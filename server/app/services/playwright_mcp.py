"""Playwright MCP服务 - 用于页面动态验证和分析。"""
import asyncio
import logging
import json
from typing import Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PlaywrightMCPService:
    """Playwright MCP服务封装 - 用于页面动态分析"""
    
    def __init__(self, project_id: str = "", headless: bool = True):
        self.project_id = project_id
        self.headless = headless
        self.browser = None
        self.context = None
        
    async def initialize(self):
        """初始化Playwright"""
        try:
            from playwright.async_api import async_playwright
            
            logger.info("[Playwright MCP] 初始化浏览器...")
            playwright = await async_playwright().start()
            
            # 启动浏览器（默认使用Chromium）
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox']
            )
            
            # 创建浏览器上下文
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Playbot/1.0'
            )
            
            logger.info("[Playwright MCP] 浏览器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"[Playwright MCP] 初始化失败: {e}", exc_info=True)
            return False
    
    async def analyze_page(
        self,
        url: str,
        page_name: str = "",
        timeout: int = 30000
    ) -> Optional[dict[str, Any]]:
        """
        分析单个页面
        
        参数:
            url: 页面URL
            page_name: 页面名称
            timeout: 超时时间（毫秒）
        
        返回:
            页面分析结果
        """
        if not self.context:
            logger.error("[Playwright MCP] 浏览器未初始化")
            return None
        
        page = None
        try:
            logger.info(f"[Playwright MCP] 访问页面: {url}")
            page = await self.context.new_page()
            
            # 访问页面
            response = await page.goto(url, wait_until='networkidle', timeout=timeout)
            
            if not response or response.status >= 400:
                logger.warning(f"[Playwright MCP] 页面访问失败: {url} (status: {response.status if response else 'N/A'})")
                return None
            
            # 等待页面完全加载
            await page.wait_for_load_state('domcontentloaded', timeout=timeout)
            await asyncio.sleep(2)  # 等待动态内容加载
            
            # 获取Accessibility Tree
            accessibility_snapshot = await self._get_accessibility_snapshot(page)
            
            # 获取页面截图（Base64）
            screenshot = await self._take_screenshot(page)
            
            # 提取交互元素
            interactive_elements = await self._extract_interactive_elements(page)
            
            # 获取页面标题和元信息
            title = await page.title()
            meta_description = await page.evaluate("""
                () => {
                    const meta = document.querySelector('meta[name="description"]');
                    return meta ? meta.content : '';
                }
            """)
            
            logger.info(f"[Playwright MCP] 页面分析完成: {page_name or url}")
            
            return {
                "url": url,
                "title": title or page_name,
                "meta_description": meta_description,
                "accessibility_tree": accessibility_snapshot,
                "screenshot": screenshot,
                "interactive_elements": interactive_elements,
                "status_code": response.status,
                "load_time": response.headers.get('x-response-time', 'N/A')
            }
            
        except Exception as e:
            logger.error(f"[Playwright MCP] 页面分析失败 {url}: {e}", exc_info=True)
            return None
        finally:
            if page:
                await page.close()
    
    async def _get_accessibility_snapshot(self, page) -> dict:
        """获取Accessibility Tree"""
        try:
            # 使用Playwright的accessibility API
            snapshot = await page.accessibility.snapshot()
            return self._simplify_snapshot(snapshot)
        except Exception as e:
            logger.warning(f"[Playwright MCP] 获取accessibility失败: {e}")
            return {}
    
    def _simplify_snapshot(self, node: dict, depth: int = 0, max_depth: int = 5) -> dict:
        """简化accessibility快照（限制深度）"""
        if depth > max_depth:
            return None
        
        simplified = {
            "role": node.get("role"),
            "name": node.get("name"),
            "value": node.get("value"),
        }
        
        # 添加关键属性
        if node.get("focused"):
            simplified["focused"] = True
        if node.get("pressed"):
            simplified["pressed"] = True
        if node.get("checked"):
            simplified["checked"] = node["checked"]
        
        # 递归处理子节点
        children = node.get("children", [])
        if children and depth < max_depth:
            simplified["children"] = [
                self._simplify_snapshot(child, depth + 1, max_depth)
                for child in children[:20]  # 限制子节点数量
            ]
        
        return simplified
    
    async def _take_screenshot(self, page) -> Optional[str]:
        """获取页面截图（Base64）"""
        try:
            screenshot_bytes = await page.screenshot(full_page=False)
            import base64
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as e:
            logger.warning(f"[Playwright MCP] 截图失败: {e}")
            return None
    
    async def _extract_interactive_elements(self, page) -> list[dict]:
        """提取交互元素"""
        try:
            elements = await page.evaluate("""
                () => {
                    const elements = [];
                    
                    // 查找所有交互元素
                    const selectors = [
                        'button', 'input', 'select', 'textarea',
                        'a[href]', '[role="button"]', '[role="tab"]',
                        '[role="checkbox"]', '[role="radio"]',
                        '[onclick]', '[tabindex="0"]'
                    ];
                    
                    selectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => {
                            const rect = el.getBoundingClientRect();
                            // 只添加可见元素
                            if (rect.width > 0 && rect.height > 0) {
                                elements.push({
                                    tag: el.tagName.toLowerCase(),
                                    type: el.type || el.getAttribute('role'),
                                    text: el.innerText?.substring(0, 100) || '',
                                    placeholder: el.placeholder || '',
                                    value: el.value || '',
                                    visible: true,
                                    position: {
                                        x: Math.round(rect.x),
                                        y: Math.round(rect.y),
                                        width: Math.round(rect.width),
                                        height: Math.round(rect.height)
                                    }
                                });
                            }
                        });
                    });
                    
                    return elements.slice(0, 50); // 限制数量
                }
            """)
            return elements
        except Exception as e:
            logger.warning(f"[Playwright MCP] 提取交互元素失败: {e}")
            return []
    
    async def verify_page_components(
        self,
        url: str,
        expected_components: list[str],
        page_name: str = ""
    ) -> dict[str, Any]:
        """
        验证页面是否包含预期组件
        
        参数:
            url: 页面URL
            expected_components: 预期组件列表
            page_name: 页面名称
        
        返回:
            验证结果
        """
        analysis = await self.analyze_page(url, page_name)
        
        if not analysis:
            return {
                "verified": False,
                "error": "页面分析失败",
                "components_found": [],
                "components_missing": expected_components
            }
        
        # 从accessibility tree中提取组件
        found_components = self._extract_components_from_tree(
            analysis.get("accessibility_tree", {})
        )
        
        # 对比预期组件
        found_set = set(found_components)
        expected_set = set(expected_components)
        
        return {
            "verified": True,
            "url": url,
            "title": analysis.get("title"),
            "components_found": list(found_set),
            "components_missing": list(expected_set - found_set),
            "components_extra": list(found_set - expected_set),
            "interactive_count": len(analysis.get("interactive_elements", [])),
            "screenshot": analysis.get("screenshot")
        }
    
    def _extract_components_from_tree(self, tree: dict) -> list[str]:
        """从accessibility tree中提取组件名称"""
        components = []
        
        def traverse(node):
            if not node:
                return
            
            # 提取组件名称
            name = node.get("name", "")
            role = node.get("role", "")
            
            if name and role not in ['generic', 'text', 'none']:
                components.append(f"{role}:{name}")
            
            # 递归子节点
            for child in node.get("children", []):
                traverse(child)
        
        traverse(tree)
        return components
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            logger.info("[Playwright MCP] 资源清理完成")
        except Exception as e:
            logger.error(f"[Playwright MCP] 清理失败: {e}")
