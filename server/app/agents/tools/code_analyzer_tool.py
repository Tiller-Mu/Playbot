"""
代码分析工具 - 供LangChain智能体使用
将code_analyzer封装为LangChain Tool，并增强分析能力
"""
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Dict, Any, Optional, List
import json
import re

from ..utils.code_analyzer import analyze_page_data, format_for_llm


class CodeAnalyzerInput(BaseModel):
    """代码分析工具输入参数"""
    source_code: str = Field(description="页面源码内容")
    file_path: str = Field(description="文件路径，用于判断文件类型（如.vue）", default="")
    analysis_depth: str = Field(
        description="分析深度: 'basic'(基础), 'deep'(深度), 'selectors'(提取选择器)",
        default="basic"
    )


class CodeAnalyzerTool(BaseTool):
    """
    代码分析工具
    
    使用AST静态分析提取Vue/React代码的关键信息：
    - 响应式变量（refs/reactive）
    - 方法定义
    - 事件处理函数
    - 生命周期钩子
    - 模板绑定事件
    - 使用的组件
    - CSS选择器（用于测试）
    
    返回结构化的代码信息，供LLM决策使用。
    """
    
    name: str = "code_analyzer"
    description: str = """分析前端页面源码，提取代码结构信息。
    
    输入: 页面源码（如Vue文件内容）、文件路径、分析深度
    输出: 结构化的代码信息
    
    分析深度选项:
    - basic: 基础信息（变量、方法、事件）
    - deep: 深度分析（包含组件关系、数据流）
    - selectors: 专门提取CSS选择器（用于测试定位元素）
    
    使用场景: 当需要了解页面代码结构，或提取测试用选择器时使用。
    """
    
    args_schema: Type[BaseModel] = CodeAnalyzerInput
    
    def _run(self, source_code: str, file_path: str = "", analysis_depth: str = "basic") -> str:
        """同步执行（不推荐，使用异步版本）"""
        raise NotImplementedError("请使用arun方法")
    
    async def _arun(self, source_code: str, file_path: str = "", analysis_depth: str = "basic") -> str:
        """
        异步执行代码分析
        
        Args:
            source_code: 页面源码
            file_path: 文件路径
            analysis_depth: 分析深度
            
        Returns:
            格式化的分析结果文本
        """
        try:
            if not source_code or len(source_code.strip()) < 10:
                return "源码为空或太短，无法分析"
            
            # 基础分析
            analysis = analyze_page_data(
                source_code=source_code,
                dom_data=None,
                file_path=file_path
            )
            
            # 根据深度决定输出
            if analysis_depth == "selectors":
                return self._extract_selectors(source_code, analysis)
            elif analysis_depth == "deep":
                return self._deep_analysis(source_code, analysis)
            else:
                # 基础分析
                return format_for_llm(analysis)
            
        except Exception as e:
            return f"代码分析失败: {str(e)}"
    
    def _extract_selectors(self, source_code: str, analysis: Dict) -> str:
        """专门提取CSS选择器（用于测试）"""
        selectors = []
        
        # 从模板中提取
        template_match = re.search(r'<template[^>]*>(.*?)</template>', source_code, re.DOTALL)
        if template_match:
            template = template_match.group(1)
            
            # 提取id选择器
            id_pattern = r'\sid=["\']([^"\']+)["\']'
            for match in re.finditer(id_pattern, template):
                selectors.append(f"#{match.group(1)}")
            
            # 提取class选择器（只取有语义的部分）
            class_pattern = r'\sclass=["\']([^"\']+)["\']'
            for match in re.finditer(class_pattern, template):
                classes = match.group(1).split()
                for cls in classes:
                    # 过滤无意义的class
                    if len(cls) > 3 and not cls.startswith('el-'):
                        selectors.append(f".{cls}")
        
        # 去重并限制数量
        unique_selectors = list(set(selectors))[:20]
        
        result = ["【CSS选择器】"]
        result.append(f"共发现 {len(unique_selectors)} 个可用选择器:\n")
        for sel in unique_selectors:
            result.append(f"  - {sel}")
        
        return '\n'.join(result)
    
    def _deep_analysis(self, source_code: str, analysis: Dict) -> str:
        """深度分析"""
        lines = []
        
        # 基础信息
        lines.append(format_for_llm(analysis))
        lines.append("\n【深度分析】")
        
        # 提取API调用
        api_pattern = r'(?:axios|fetch)\.[a-z]+\s*\(\s*["\']([^"\']+)["\']'
        api_calls = re.findall(api_pattern, source_code)
        if api_calls:
            lines.append("\nAPI端点:")
            for api in set(api_calls)[:5]:
                lines.append(f"  - {api}")
        
        # 提取路由跳转
        router_pattern = r'router\.(push|replace)\s*\(\s*["\']([^"\']+)["\']'
        routes = re.findall(router_pattern, source_code)
        if routes:
            lines.append("\n路由跳转:")
            for action, route in routes[:5]:
                lines.append(f"  - {action}: {route}")
        
        # 提取验证逻辑
        validate_pattern = r'(?:validate|check|verify)[A-Z]\w*\s*\('
        validators = re.findall(validate_pattern, source_code)
        if validators:
            lines.append("\n验证方法:")
            for v in set(validators)[:5]:
                lines.append(f"  - {v}")
        
        return '\n'.join(lines)


# 便捷函数，直接调用
async def analyze_code(
    source_code: str, 
    file_path: str = "", 
    analysis_depth: str = "basic"
) -> str:
    """
    便捷函数：直接分析代码
    
    Args:
        source_code: 页面源码
        file_path: 文件路径
        analysis_depth: 分析深度
        
    Returns:
        分析结果文本
    """
    tool = CodeAnalyzerTool()
    return await tool.arun(
        source_code=source_code, 
        file_path=file_path,
        analysis_depth=analysis_depth
    )
