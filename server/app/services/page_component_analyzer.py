"""页面级MCP分析器 - 使用LLM分析单个页面的组件引用关系。"""
import json
import logging
import re
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
                description = analysis_result.get("description", "")
                
                # 日志输出包含description
                log_detail = {"route": page_route, "components": components}
                if description:
                    log_detail["description"] = description
                
                await self._send_log("success", 
                    f"页面 {page_name} 分析完成，发现 {len(components)} 个组件",
                    log_detail
                )
                
                return {
                    "route": page_route,
                    "url": "",
                    "title": analysis_result.get("page_name", page_name),
                    "description": description,
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
        """使用LLM基于命名推断页面功能（简化版，不传完整代码）"""
        
        # 从组件清单中提取组件名列表
        component_names = []
        for line in components_summary.split('\n'):
            # 格式: "- ComponentName (path) - type"
            match = re.search(r'-\s+(\w+)\s+\(', line)
            if match:
                component_names.append(match.group(1))
        
        # 构建组件列表字符串
        component_list_str = '\n'.join(['- ' + name for name in component_names[:15]])
        
        prompt = f"""你是一个前端页面分析专家。请根据页面名称和组件列表，推断页面的核心功能。

## 页面信息
- 页面名称: {page_name}
- 路由路径: {page_route}

## 页面使用的组件
{component_list_str}  # 最多15个组件

## 分析任务

根据页面名称和组件名，用**一句话**描述这个页面的核心功能。

**命名规律参考**：
- List/Table结尾 → 列表展示页面
- Form结尾 → 表单编辑页面  
- Detail/View结尾 → 详情展示页面
- Dashboard → 数据仪表盘
- Login/Register → 登录注册页面
- Chart/Graph → 图表统计页面
- Modal/Dialog → 弹窗组件（不是独立页面）

**输出要求**：
- 必须使用**中文**
- 一句话描述，20-50字
- 包含主要功能和操作

## 输出格式（JSON）

```json
{{
  "page_name": "{page_name}",
  "description": "用户列表页面，展示用户信息并支持搜索、分页和编辑操作",
  "components": {component_names[:10]}  // 最多返回10个组件
}}
```

**注意**：
- 只返回JSON，不要其他内容
- description必须是一句话
- components返回组件名数组即可

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
                logger.debug(f"LLM原始响应: {response[:500]}...")  # 记录原始响应用于调试
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
