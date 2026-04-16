"""
DOM提取工具 - 供LangChain智能体使用
增强版：支持更多提取类型和测试用选择器生成
"""
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, List, Dict, Any, Optional
import json
import re

from ..utils.code_analyzer import DOMAnalyzer


class DOMExtractorInput(BaseModel):
    """DOM提取工具输入参数"""
    dom_data: str = Field(description="DOM数据（JSON字符串或字典）")
    extract_type: str = Field(
        description="提取类型: 'interactive'(交互元素), 'forms'(表单), 'selectors'(测试选择器), 'all'(全部)",
        default="interactive"
    )


class DOMExtractorTool(BaseTool):
    """
    DOM提取工具
    
    从页面DOM数据中提取关键信息：
    - 交互元素（按钮、输入框、链接等）
    - 表单结构
    - 事件绑定
    - 测试用CSS选择器（自动生成）
    
    返回精简后的DOM信息，供LLM决策使用。
    """
    
    name: str = "dom_extractor"
    description: str = """提取页面DOM中的关键信息。
    
    输入: DOM数据（从录制或实时获取）、提取类型
    输出: 结构化的DOM信息
    
    提取类型:
    - interactive: 交互元素（按钮、输入框等）
    - forms: 表单结构
    - selectors: 生成测试用CSS选择器（推荐用于生成测试代码）
    - all: 全部信息
    
    使用场景: 当需要了解页面可交互元素，或生成测试用选择器时使用。
    """
    
    args_schema: Type[BaseModel] = DOMExtractorInput
    
    def _run(self, dom_data: str, extract_type: str = "interactive") -> str:
        """同步执行（不推荐）"""
        raise NotImplementedError("请使用arun方法")
    
    async def _arun(self, dom_data: str, extract_type: str = "interactive") -> str:
        """
        异步执行DOM提取
        
        Args:
            dom_data: DOM数据（JSON字符串）
            extract_type: 提取类型
            
        Returns:
            格式化的DOM信息
        """
        try:
            # 解析DOM数据
            if isinstance(dom_data, str):
                try:
                    data = json.loads(dom_data)
                except json.JSONDecodeError:
                    return f"DOM数据解析失败，请提供有效的JSON"
            else:
                data = dom_data
            
            # 根据类型提取
            if extract_type == "selectors":
                return self._extract_selectors(data)
            
            result_lines = ["【DOM分析结果】"]
            
            # 提取交互元素
            if extract_type in ["interactive", "all"]:
                elements = DOMAnalyzer.extract_interactive_elements(data)
                result_lines.append(f"\n交互元素: {len(elements)}个")
                
                if elements:
                    result_lines.append("主要元素:")
                    for elem in elements[:15]:  # 增加数量
                        tag = elem.get('tag', '')
                        elem_id = elem.get('id', '')
                        elem_class = elem.get('class', '')
                        text = elem.get('text', '')[:30]
                        events = ', '.join(elem.get('events', [])[:3])
                        
                        parts = [f"  - {tag}"]
                        if elem_id:
                            parts.append(f"id={elem_id}")
                        if elem_class:
                            parts.append(f"class={elem_class[:20]}")
                        if text:
                            parts.append(f"text='{text}'")
                        if events:
                            parts.append(f"events=[{events}]")
                        
                        result_lines.append(' '.join(parts))
            
            # 提取表单
            if extract_type in ["forms", "all"]:
                forms = DOMAnalyzer.extract_forms(data)
                result_lines.append(f"\n表单数量: {len(forms)}")
                
                for i, form in enumerate(forms[:5], 1):  # 增加数量
                    form_id = form.get('id', f'form_{i}')
                    fields = form.get('fields', [])
                    field_info = []
                    for f in fields[:8]:  # 增加数量
                        name = f.get('name', f.get('id', '?'))
                        ftype = f.get('type', 'text')
                        required = "*" if f.get('required') else ""
                        placeholder = f.get('placeholder', '')[:15]
                        info = f"{name}({ftype}){required}"
                        if placeholder:
                            info += f"'{placeholder}'"
                        field_info.append(info)
                    
                    result_lines.append(f"  表单 {form_id}:")
                    result_lines.append(f"    字段: {', '.join(field_info)}")
                    
                    # 添加提交按钮信息
                    submit = form.get('submit_button')
                    if submit:
                        result_lines.append(f"    提交: {submit.get('text', submit.get('id', 'submit'))}")
            
            # 统计信息
            if extract_type == "all":
                result_lines.append("\n【统计】")
                all_elements = self._count_elements(data)
                result_lines.append(f"  总元素数: {all_elements.get('total', 0)}")
                result_lines.append(f"  按钮: {all_elements.get('button', 0)}")
                result_lines.append(f"  输入框: {all_elements.get('input', 0)}")
                result_lines.append(f"  链接: {all_elements.get('a', 0)}")
            
            return '\n'.join(result_lines)
            
        except Exception as e:
            return f"DOM提取失败: {str(e)}"
    
    def _extract_selectors(self, data: Dict) -> str:
        """提取测试用CSS选择器"""
        selectors = {
            "high_confidence": [],  # 有id或唯一class
            "medium_confidence": [],  # 有特定属性
            "low_confidence": []  # 只有tag
        }
        
        elements = DOMAnalyzer.extract_interactive_elements(data)
        
        for elem in elements:
            tag = elem.get('tag', '')
            elem_id = elem.get('id', '')
            elem_class = elem.get('class', '')
            text = elem.get('text', '')[:20]
            
            # 高置信度：有id
            if elem_id:
                selector = f"#{elem_id}"
                desc = f"{tag}"
                if text:
                    desc += f" '{text}'"
                selectors["high_confidence"].append((selector, desc))
                continue
            
            # 中置信度：有语义化class
            if elem_class:
                classes = elem_class.split()
                meaningful = [c for c in classes if len(c) > 3 and not c.startswith(('el-', 'ant-'))]
                if meaningful:
                    selector = f"{tag}.{meaningful[0]}"
                    desc = f"{tag}"
                    if text:
                        desc += f" '{text}'"
                    selectors["medium_confidence"].append((selector, desc))
                    continue
            
            # 低置信度：只有tag和text
            if text and len(text) > 2:
                # 使用text定位
                selector = f"{tag}:has-text(\"{text}\")"
                selectors["low_confidence"].append((selector, f"{tag} '{text}'"))
        
        # 生成结果
        lines = ["【测试用CSS选择器】"]
        lines.append(f"\n高置信度（推荐）: {len(selectors['high_confidence'])}个")
        for sel, desc in selectors["high_confidence"][:10]:
            lines.append(f"  page.locator('{sel}')  # {desc}")
        
        if selectors["medium_confidence"]:
            lines.append(f"\n中置信度: {len(selectors['medium_confidence'])}个")
            for sel, desc in selectors["medium_confidence"][:8]:
                lines.append(f"  page.locator('{sel}')  # {desc}")
        
        if selectors["low_confidence"]:
            lines.append(f"\n低置信度（可能不稳定）: {len(selectors['low_confidence'])}个")
            for sel, desc in selectors["low_confidence"][:5]:
                lines.append(f"  page.locator('{sel}')  # {desc}")
        
        return '\n'.join(lines)
    
    def _count_elements(self, data: Dict) -> Dict[str, int]:
        """统计元素数量"""
        counts = {"total": 0, "button": 0, "input": 0, "a": 0}
        
        def traverse(node):
            if not isinstance(node, dict):
                return
            
            tag = node.get('tag', '').lower()
            counts["total"] += 1
            
            if tag in counts:
                counts[tag] += 1
            
            for child in node.get('children', []):
                traverse(child)
        
        traverse(data)
        return counts


# 便捷函数
async def extract_dom(dom_data: Any, extract_type: str = "interactive") -> str:
    """
    便捷函数：直接提取DOM信息
    
    Args:
        dom_data: DOM数据
        extract_type: 提取类型
        
    Returns:
        提取结果文本
    """
    tool = DOMExtractorTool()
    dom_str = json.dumps(dom_data) if not isinstance(dom_data, str) else dom_data
    return await tool.arun(dom_data=dom_str, extract_type=extract_type)
