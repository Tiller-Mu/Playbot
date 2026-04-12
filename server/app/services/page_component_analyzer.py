"""页面级MCP分析器 - 使用LLM分析单个页面的组件引用关系。"""
import json
import logging
from pathlib import Path
from typing import Any, Optional, Callable

from app.services.llm_service import llm_chat_json
from app.services.mcp_log_service import mcp_log_service

logger = logging.getLogger(__name__)


class PageComponentAnalyzer:
    """页面组件分析器 - 为单个页面启动独立的MCP会话"""
    
    def __init__(self, repo_path: str, project_id: str = "", log_callback: Optional[Callable] = None):
        self.repo_path = Path(repo_path)
        self.project_id = project_id
        self.log_callback = log_callback  # 实时日志回调
    
    async def _send_log(self, level: str, message: str, data: Any = None):
        """发送实时日志"""
        if self.project_id:
            mcp_log_service.log(self.project_id, level, message, data)
        if self.log_callback:
            import asyncio
            # 如果是异步函数，需要await
            if asyncio.iscoroutinefunction(self.log_callback):
                await self.log_callback(level, message, data)
            else:
                self.log_callback(level, message, data)
    
    async def analyze_page(
        self,
        page_component: dict,
        components_list: list[dict],
        global_rules: str = ""
    ) -> Optional[dict[str, Any]]:
        """
        分析单个页面的组件引用关系
        
        参数:
            page_component: 页面组件信息 {name, file_path, type, route}
            components_list: 所有组件清单（防止MCP遗漏）
            global_rules: 全局规则
        
        返回:
            页面分析报告
        """
        page_name = page_component.get("name", "Unknown")
        page_route = page_component.get("route", "")
        
        try:
            page_file_path = self.repo_path / page_component["file_path"]
            
            if not page_file_path.exists():
                logger.warning(f"页面文件不存在: {page_file_path}")
                await self._send_log("warning", f"页面文件不存在: {page_file_path}")
                return None
            
            # 读取页面源码
            page_source = page_file_path.read_text(encoding="utf-8", errors="ignore")
            await self._send_log("info", f"读取页面文件: {page_component['file_path']} ({len(page_source)} 字符)")
            
            # 构建组件清单
            components_summary = self._build_components_summary(components_list)
            await self._send_log("debug", f"组件清单已构建: {len(components_list)} 个组件")
            
            # 使用LLM分析页面
            await self._send_log("info", f"开始LLM分析页面: {page_name}")
            analysis_result = await self._analyze_with_llm(
                page_name=page_name,
                page_route=page_route,
                page_source=page_source,
                components_summary=components_summary,
                global_rules=global_rules
            )
            
            if analysis_result:
                components = analysis_result.get("components", [])
                await self._send_log("success", 
                    f"页面 {page_name} 分析完成，发现 {len(components)} 个组件",
                    {"route": page_route, "components": components}
                )
                
                return {
                    "route": page_route,
                    "url": "",
                    "title": analysis_result.get("page_name", page_name),
                    "detected_components": components,
                    "interactive_elements": analysis_result.get("interactive_elements", []),
                    "modals": analysis_result.get("modals", []),
                    "forms": analysis_result.get("forms", []),
                    "navigation_links": analysis_result.get("navigation_links", []),
                    "discovered_from": "mcp_llm_analysis",
                    "source_file": page_component["file_path"]
                }
            else:
                await self._send_log("error", f"页面 {page_name} 分析失败")
                return None
            
        except Exception as e:
            logger.error(f"分析页面失败 {page_component.get('file_path', '')}: {e}", exc_info=True)
            await self._send_log("error", f"分析页面异常: {str(e)}")
            return None
    
    def _build_components_summary(self, components_list: list[dict]) -> str:
        """
        构建组件清单摘要（防止MCP遗漏）
        
        格式：
        - UserForm (src/components/UserForm.vue) - component
        - LoginPage (src/views/LoginPage.vue) - page [/login]
        """
        summary_lines = []
        for comp in components_list:
            name = comp.get("name", "Unknown")
            file_path = comp.get("file_path", "")
            comp_type = comp.get("type", "component")
            route = comp.get("route", "")
            
            if comp_type == "page" and route:
                summary_lines.append(f"- {name} ({file_path}) - page [{route}]")
            else:
                summary_lines.append(f"- {name} ({file_path}) - {comp_type}")
        
        return "\n".join(summary_lines)
    
    async def _analyze_with_llm(
        self,
        page_name: str,
        page_route: str,
        page_source: str,
        components_summary: str,
        global_rules: str
    ) -> Optional[dict]:
        """使用LLM分析页面组件引用关系"""
        
        prompt = f"""你是一个前端页面分析专家。请分析以下页面的组件结构和交互元素。

## 页面信息
- 页面名称: {page_name}
- 路由路径: {page_route}

## 可用组件清单（参考，防止遗漏）
{components_summary}

## 当前页面源码
```
{page_source[:8000]}  # 限制长度，避免token过多
```

{"## 全局规则\n" + global_rules if global_rules else ""}

## 分析任务

1. **追踪组件引用**
   - 从import语句中找出所有使用的组件
   - 追踪被引用组件的import（最多2层深度）
   - 对于每个组件，判断：
     * 页面内组件（Modal、Dialog、Form等）✓ 纳入
     * 路由跳转组件（router-link、Link等）✗ 不纳入components，但记录到navigation_links

2. **识别交互元素**
   - 表单（Form）、输入框（Input）、按钮（Button）
   - 弹窗（Modal/Dialog）
   - 下拉菜单（Select/Dropdown）
   - Tab切换、折叠面板
   - 条件渲染的内容区块

3. **边界规则**
   - ✓ 分析：当前页面 + 子组件（import链）
   - ✓ 分析：页面内弹出的表单、对话框
   - ✗ 排除：router-link跳转的其他页面
   - ✗ 排除：window.location.href跳转
   - ✗ 排除：任何会导致路由变化的交互

## 输出格式（JSON）

```json
{{
  "page_name": "用户管理",
  "components": ["UserTable", "UserForm", "DeleteConfirmModal"],
  "interactive_elements": [
    {{"type": "button", "text": "提交"}},
    {{"type": "input", "placeholder": "请输入用户名"}}
  ],
  "modals": ["DeleteConfirmModal", "UserFormModal"],
  "forms": ["UserForm"],
  "navigation_links": [
    {{"text": "返回首页", "route": "/"}},
    {{"text": "用户详情", "route": "/user/:id"}}
  ]
}}
```

请只输出JSON，不要其他内容。"""

        try:
            # 使用JSON格式响应
            response = await llm_chat_json(
                messages=[
                    {"role": "system", "content": "你是一个专业的前端页面分析专家，擅长分析Vue/React组件结构。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4096
            )
            
            # 解析JSON响应
            result = self._parse_llm_response(response)
            
            if result:
                logger.info(f"LLM分析页面成功: {page_name}")
                logger.debug(f"分析结果: {json.dumps(result, ensure_ascii=False)[:200]}...")
                return result
            else:
                logger.warning(f"LLM分析页面失败，无法解析响应: {page_name}")
                return None
                
        except Exception as e:
            logger.error(f"LLM分析页面异常 {page_name}: {e}", exc_info=True)
            return None
    
    def _parse_llm_response(self, response: str) -> Optional[dict]:
        """解析LLM的JSON响应"""
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取JSON块
            try:
                # 查找 ```json ... ``` 块
                import re
                json_match = re.search(r'```json\s*\n(.*?)\n```', response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                
                # 查找第一个 { 到最后一个 }
                start = response.find('{')
                end = response.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(response[start:end+1])
                
                return None
            except Exception as e:
                logger.warning(f"解析LLM响应失败: {e}")
                return None
