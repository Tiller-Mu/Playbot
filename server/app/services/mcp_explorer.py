"""MCP 页面分析服务 - 通过独立MCP会话分析每个页面的组件结构。"""
import re
import json
import logging
import asyncio
from pathlib import Path
from typing import Any, Optional, Callable

from app.services.page_component_analyzer import PageComponentAnalyzer

logger = logging.getLogger(__name__)


class MCPPageExplorer:
    """MCP 页面分析器 - 为每个页面启动独立的MCP会话分析组件引用"""
    
    def __init__(self, repo_path: str, project_id: str = "", log_callback: Optional[Callable] = None):
        self.repo_path = repo_path
        self.project_id = project_id
        self.log_callback = log_callback
        self.analysis_log = []
    
    async def discover_pages(
        self,
        base_url: str,
        entry_points: list[str],
        components_info: dict,
        headless: bool = True,
        global_rules: str = "",
        concurrent: bool = False
    ) -> list[dict[str, Any]]:
        """
        通过独立MCP会话逐个分析页面
        
        优化说明：
        - 每个页面使用独立的MCP会话（避免上下文污染）
        - 传入组件清单作为参考（防止遗漏）
        - 分析边界：当前页面 + 子组件，排除路由跳转
        
        参数:
            base_url: 站点根 URL
            entry_points: 入口点列表（从静态分析获取）
            components_info: 组件信息（包含完整的组件清单）
            headless: 是否使用无头模式（保留参数，目前不使用）
            global_rules: 全局规则
            concurrent: 是否并发分析多个页面（默认串行，便于调试）
        
        返回:
            页面列表，每个页面包含路由、URL、标题、检测到的组件等信息
        """
        logger.info(f"[MCP 页面分析] 开始分析 {len(entry_points)} 个页面")
        logger.info(f"[MCP 页面分析] 组件总数: {len(components_info.get('components', []))}")
        
        discovered_pages = []
        page_components = components_info.get("page_components", [])
        components_list = components_info.get("components", [])
        
        # 创建页面分析器（传入project_id和log_callback用于日志）
        page_analyzer = PageComponentAnalyzer(
            repo_path=self.repo_path,
            project_id=self.project_id,
            log_callback=self.log_callback
        )
        
        if concurrent:
            # 并发分析（快速但日志可能交错）
            tasks = [
                self._analyze_single_page(page_comp, components_list, global_rules, page_analyzer)
                for page_comp in page_components
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict) and result:
                    discovered_pages.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"页面分析异常: {result}")
        else:
            # 串行分析（便于调试和日志查看）
            for page_comp in page_components:
                page_info = await self._analyze_single_page(
                    page_comp, components_list, global_rules, page_analyzer
                )
                if page_info:
                    discovered_pages.append(page_info)
        
        # 填充URL
        for page_info in discovered_pages:
            if page_info.get("route"):
                page_info["url"] = f"{base_url.rstrip('/')}{page_info['route']}"
        
        logger.info(f"[MCP 页面分析] 完成，共发现 {len(discovered_pages)} 个页面")
        
        return discovered_pages
    
    async def _analyze_single_page(
        self,
        page_comp: dict,
        components_list: list[dict],
        global_rules: str,
        page_analyzer: PageComponentAnalyzer
    ) -> Optional[dict[str, Any]]:
        """
        分析单个页面（独立MCP会话）
        
        参数:
            page_comp: 页面组件信息
            components_list: 所有组件清单
            global_rules: 全局规则
            page_analyzer: 页面分析器实例
        
        返回:
            页面分析结果
        """
        route = page_comp.get("route", "")
        logger.info(f"[MCP 页面分析] 开始分析页面: {route} ({page_comp.get('name', '')})")
        
        try:
            # 使用LLM分析页面组件引用
            page_info = await page_analyzer.analyze_page(
                page_component=page_comp,
                components_list=components_list,
                global_rules=global_rules
            )
            
            if page_info:
                logger.info(
                    f"[MCP 页面分析] 页面分析完成: {route} - "
                    f"发现 {len(page_info.get('detected_components', []))} 个组件"
                )
                return page_info
            else:
                logger.warning(f"[MCP 页面分析] 页面分析失败: {route}")
                return None
                
        except Exception as e:
            logger.error(f"[MCP 页面分析] 页面分析异常 {route}: {e}", exc_info=True)
            return None
    
    async def cleanup(self):
        """清理资源"""
        pass

