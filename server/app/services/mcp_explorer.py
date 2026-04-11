"""MCP 页面分析服务 - 通过静态代码分析发现页面结构。"""
import re
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MCPPageExplorer:
    """MCP 页面分析器 - 静态分析代码，生成页面树"""
    
    def __init__(self):
        self.analysis_log = []
    
    async def discover_pages(
        self,
        base_url: str,
        entry_points: list[str],
        components_info: dict,
        headless: bool = True,
        global_rules: str = ""
    ) -> list[dict[str, Any]]:
        """
        通过静态代码分析发现所有页面
        
        参数:
            base_url: 站点根 URL（用于后续执行，这里不使用）
            entry_points: 入口点列表（从静态分析获取）
            components_info: 组件信息
            headless: 是否使用无头模式（这里不使用）
            global_rules: 全局规则
        
        返回:
            页面列表，每个页面包含路由、URL、标题、检测到的组件等信息
        """
        logger.info(f"[MCP 静态分析] 开始分析 {len(entry_points)} 个入口点")
        logger.info(f"[MCP 静态分析] 入口点列表: {entry_points}")
        
        discovered_pages = []
        
        # 从组件信息中提取页面
        page_components = components_info.get("page_components", [])
        common_components = components_info.get("common_components", [])
        
        for page_comp in page_components:
            page_info = self._analyze_page(page_comp, common_components, base_url)
            if page_info:
                discovered_pages.append(page_info)
                logger.info(f"[MCP 静态分析] 发现页面: {page_info['route']}")
        
        logger.info(f"[MCP 静态分析] 完成，共发现 {len(discovered_pages)} 个页面")
        
        return discovered_pages
    
    def _analyze_page(
        self,
        page_component: dict,
        all_components: list[dict],
        base_url: str
    ) -> dict[str, Any] | None:
        """分析单个页面组件"""
        try:
            route = page_component.get("route", "")
            if not route:
                return None
            
            file_path = page_component.get("file_path", "")
            component_name = page_component.get("name", "")
            
            # 读取页面文件内容
            page_content = ""
            if file_path:
                try:
                    page_content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    logger.warning(f"读取页面文件失败 {file_path}: {e}")
            
            # 分析页面中使用的组件
            used_components = self._detect_used_components(page_content, all_components)
            
            # 分析页面交互元素
            interactive_elements = self._extract_interactive_elements(page_content)
            
            # 分析页面中的链接
            internal_links = self._extract_internal_links(page_content, base_url)
            
            return {
                "route": route,
                "url": f"{base_url.rstrip('/')}{route}",
                "title": component_name,
                "detected_components": used_components,
                "screenshot_path": "",  # 静态分析没有截图
                "dom_summary": {
                    "interactiveElements": interactive_elements,
                    "totalElements": len(interactive_elements)
                },
                "internal_links": internal_links,
                "discovered_from": "static_analysis",
                "source_file": file_path
            }
        except Exception as e:
            logger.error(f"分析页面失败 {page_component.get('file_path', '')}: {e}")
            return None
    
    def _detect_used_components(self, page_content: str, all_components: list[dict]) -> list[str]:
        """检测页面中使用了哪些组件"""
        used = []
        
        for comp in all_components:
            comp_name = comp.get("name", "")
            if comp_name and comp_name in page_content:
                used.append(comp_name)
        
        return used
    
    def _extract_interactive_elements(self, content: str) -> list[dict]:
        """从代码中提取交互元素"""
        elements = []
        
        # 匹配 button 元素
        buttons = re.findall(r'<button[^>]*>(.*?)</button>', content, re.DOTALL)
        for btn_text in buttons:
            clean_text = re.sub(r'<[^>]+>', '', btn_text).strip()[:50]
            if clean_text:
                elements.append({
                    "type": "button",
                    "text": clean_text,
                    "visible": True
                })
        
        # 匹配 input 元素
        inputs = re.findall(r'<input[^>]*>', content)
        for input_tag in inputs:
            input_type = re.search(r'type=["\']([^"\']+)["\']', input_tag)
            input_name = re.search(r'name=["\']([^"\']+)["\']', input_tag)
            input_placeholder = re.search(r'placeholder=["\']([^"\']+)["\']', input_tag)
            
            elements.append({
                "type": "input",
                "inputType": input_type.group(1) if input_type else "text",
                "name": input_name.group(1) if input_name else "",
                "placeholder": input_placeholder.group(1) if input_placeholder else "",
                "visible": True
            })
        
        # 匹配链接
        links = re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', content, re.DOTALL)
        for href, link_text in links:
            clean_text = re.sub(r'<[^>]+>', '', link_text).strip()[:50]
            if href and not href.startswith(('javascript:', 'mailto:', '#')):
                elements.append({
                    "type": "link",
                    "text": clean_text,
                    "href": href,
                    "visible": True
                })
        
        return elements
    
    def _extract_internal_links(self, content: str, base_url: str) -> list[dict]:
        """提取页面中的内部链接"""
        links = []
        
        # 匹配 router-link（Vue Router）
        router_links = re.findall(r'<router-link[^>]*to=["\']([^"\']+)["\'][^>]*>(.*?)</router-link>', content, re.DOTALL)
        for path, link_text in router_links:
            clean_text = re.sub(r'<[^>]+>', '', link_text).strip()
            links.append({
                "text": clean_text,
                "href": path,
                "absolute_url": f"{base_url.rstrip('/')}{path}",
                "path": path,
                "is_internal": True,
                "explored": False
            })
        
        # 匹配普通链接
        href_links = re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', content, re.DOTALL)
        for href, link_text in href_links:
            if href.startswith('/') or href.startswith('./'):
                clean_text = re.sub(r'<[^>]+>', '', link_text).strip()
                links.append({
                    "text": clean_text,
                    "href": href,
                    "absolute_url": f"{base_url.rstrip('/')}{href.lstrip('./')}",
                    "path": href,
                    "is_internal": True,
                    "explored": False
                })
        
        return links
    
    async def cleanup(self):
        """清理资源（静态分析无需清理）"""
        pass

