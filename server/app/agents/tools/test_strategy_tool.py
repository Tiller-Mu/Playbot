"""
测试策略工具 - 基于代码和DOM分析，建议测试策略
"""
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Dict, Any, List
import json


class TestStrategyInput(BaseModel):
    """测试策略工具输入参数"""
    code_analysis: str = Field(description="代码分析结果")
    dom_analysis: str = Field(description="DOM分析结果")
    page_path: str = Field(description="页面路径", default="")


class TestStrategyTool(BaseTool):
    """
    测试策略建议工具
    
    基于代码分析和DOM分析，智能推荐测试策略：
    - 应该测试哪些功能点
    - 推荐的测试顺序
    - 需要关注的风险点
    - 建议的测试类型（单元/集成/E2E）
    
    这个工具不直接生成代码，而是提供测试规划建议。
    """
    
    name: str = "test_strategy"
    description: str = """基于代码和DOM分析，提供测试策略建议。
    
    输入: 代码分析结果、DOM分析结果、页面路径
    输出: 测试策略建议，包括：
    - 推荐测试的功能点
    - 测试优先级
    - 风险点提示
    - 建议的测试类型
    
    使用场景: 在生成具体测试代码前，先规划测试策略。
    """
    
    args_schema: Type[BaseModel] = TestStrategyInput
    
    def _run(self, code_analysis: str, dom_analysis: str, page_path: str = "") -> str:
        """同步执行（不推荐）"""
        raise NotImplementedError("请使用arun方法")
    
    async def _arun(self, code_analysis: str, dom_analysis: str, page_path: str = "") -> str:
        """
        异步执行策略分析
        
        Args:
            code_analysis: 代码分析结果
            dom_analysis: DOM分析结果
            page_path: 页面路径
            
        Returns:
            测试策略建议
        """
        try:
            suggestions = []
            
            # 分析代码中的关键功能
            suggestions.extend(self._analyze_code_features(code_analysis))
            
            # 分析DOM中的交互点
            suggestions.extend(self._analyze_dom_features(dom_analysis))
            
            # 生成策略报告
            return self._format_strategy(suggestions, page_path)
            
        except Exception as e:
            return f"策略分析失败: {str(e)}"
    
    def _analyze_code_features(self, code_analysis: str) -> List[Dict]:
        """从代码分析中提取功能点"""
        features = []
        
        # 检查表单提交
        if "form" in code_analysis.lower() or "submit" in code_analysis.lower():
            features.append({
                "name": "表单提交",
                "priority": "高",
                "type": "功能测试",
                "reason": "页面包含表单，需要验证提交功能"
            })
        
        # 检查API调用
        if "api" in code_analysis.lower() or "axios" in code_analysis.lower():
            features.append({
                "name": "API集成",
                "priority": "高",
                "type": "集成测试",
                "reason": "页面有后端API调用，需要验证数据交互"
            })
        
        # 检查路由跳转
        if "router" in code_analysis.lower() or "push" in code_analysis.lower():
            features.append({
                "name": "路由导航",
                "priority": "中",
                "type": "导航测试",
                "reason": "页面有路由跳转逻辑"
            })
        
        # 检查验证逻辑
        if "validate" in code_analysis.lower() or "check" in code_analysis.lower():
            features.append({
                "name": "输入验证",
                "priority": "高",
                "type": "边界测试",
                "reason": "页面有输入验证，需要测试各种边界情况"
            })
        
        # 检查响应式变量
        if "ref(" in code_analysis or "reactive(" in code_analysis:
            features.append({
                "name": "状态管理",
                "priority": "中",
                "type": "状态测试",
                "reason": "页面使用响应式状态，需要验证状态变化"
            })
        
        return features
    
    def _analyze_dom_features(self, dom_analysis: str) -> List[Dict]:
        """从DOM分析中提取交互点"""
        features = []
        
        # 检查按钮
        if "button" in dom_analysis.lower():
            features.append({
                "name": "按钮交互",
                "priority": "高",
                "type": "交互测试",
                "reason": "页面有按钮元素，需要测试点击行为"
            })
        
        # 检查输入框
        if "input" in dom_analysis.lower():
            features.append({
                "name": "输入交互",
                "priority": "高",
                "type": "交互测试",
                "reason": "页面有输入框，需要测试输入和验证"
            })
        
        # 检查链接
        if "a " in dom_analysis.lower() or "link" in dom_analysis.lower():
            features.append({
                "name": "链接导航",
                "priority": "低",
                "type": "导航测试",
                "reason": "页面有链接，需要测试跳转"
            })
        
        # 检查表格
        if "table" in dom_analysis.lower():
            features.append({
                "name": "表格数据",
                "priority": "中",
                "type": "数据测试",
                "reason": "页面有表格，需要验证数据展示"
            })
        
        return features
    
    def _format_strategy(self, features: List[Dict], page_path: str) -> str:
        """格式化策略报告"""
        if not features:
            return "【测试策略建议】\n\n未识别到明显的测试点，建议进行基础渲染测试。"
        
        lines = ["【测试策略建议】"]
        
        if page_path:
            lines.append(f"\n页面: {page_path}")
        
        # 按优先级分组
        high = [f for f in features if f["priority"] == "高"]
        medium = [f for f in features if f["priority"] == "中"]
        low = [f for f in features if f["priority"] == "低"]
        
        if high:
            lines.append("\n🔴 高优先级测试:")
            for f in high:
                lines.append(f"  • {f['name']} ({f['type']})")
                lines.append(f"    原因: {f['reason']}")
        
        if medium:
            lines.append("\n🟡 中优先级测试:")
            for f in medium:
                lines.append(f"  • {f['name']} ({f['type']})")
        
        if low:
            lines.append("\n🟢 低优先级测试:")
            for f in low:
                lines.append(f"  • {f['name']} ({f['type']})")
        
        # 建议的测试用例数量
        total = len(features)
        suggested = min(total, 3)  # 建议最多3个
        lines.append(f"\n💡 建议生成 {suggested} 个核心测试用例")
        
        return '\n'.join(lines)


# 便捷函数
async def suggest_test_strategy(
    code_analysis: str,
    dom_analysis: str,
    page_path: str = ""
) -> str:
    """
    便捷函数：获取测试策略建议
    
    Args:
        code_analysis: 代码分析结果
        dom_analysis: DOM分析结果
        page_path: 页面路径
        
    Returns:
        策略建议文本
    """
    tool = TestStrategyTool()
    return await tool.arun(
        code_analysis=code_analysis,
        dom_analysis=dom_analysis,
        page_path=page_path
    )
