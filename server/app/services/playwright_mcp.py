"""Playwright MCP服务 - 用于页面动态验证和分析。

使用纯同步API，在独立线程中运行，避免Windows asyncio子进程问题。
"""
import logging
import json
import base64
import threading
from typing import Any, Optional
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class PlaywrightMCPService:
    """Playwright MCP服务封装 - 使用独立线程运行同步API"""
    
    def __init__(self, project_id: str = "", headless: bool = True):
        self.project_id = project_id
        self.headless = headless
        self._playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._thread = None
        self._result = None
        self._error = None
        self._event = threading.Event()
        
    def _run_in_thread(self, func, *args, **kwargs):
        """在独立线程中执行Playwright操作"""
        def thread_target():
            try:
                # 每个线程需要自己的playwright实例
                playwright = sync_playwright().start()
                
                browser = playwright.chromium.launch(
                    headless=self.headless,
                    args=['--no-sandbox']
                )
                
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Playbot/1.0'
                )
                
                # 执行操作
                result = func(context, browser, *args, **kwargs)
                
                # 清理
                browser.close()
                playwright.stop()
                
                self._result = result
            except Exception as e:
                logger.error(f"[Playwright MCP] 线程执行失败: {e}", exc_info=True)
                self._error = e
            finally:
                self._event.set()
        
        self._thread = threading.Thread(target=thread_target, daemon=True)
        self._thread.start()
        self._event.wait(timeout=60)  # 等待60秒
        
        if self._error:
            raise self._error
        
        return self._result
    
    def _analyze_page_sync(self, context, browser, url: str, page_name: str, timeout: int) -> Optional[dict]:
        """在独立线程中分析页面"""
        page = None
        try:
            logger.info(f"[Playwright MCP] 访问页面: {url}")
            page = context.new_page()
            
            # 访问页面
            response = page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            
            if not response or response.status >= 400:
                logger.warning(f"[Playwright MCP] 页面访问失败: {url} (status: {response.status if response else 'N/A'})")
                return None
            
            # 等待页面完全加载
            page.wait_for_load_state('domcontentloaded', timeout=timeout)
            import time
            time.sleep(2)  # 等待动态内容加载
            
            # 获取页面标题和元信息
            title = page.title()
            meta_description = page.evaluate("""
                () => {
                    const meta = document.querySelector('meta[name="description"]');
                    return meta ? meta.content : '';
                }
            """)
            
            # 提取交互元素
            interactive_elements = page.evaluate("""
                () => {
                    const elements = [];
                    const selectors = [
                        'button', 'input', 'select', 'textarea',
                        'a[href]', '[role="button"]', '[role="tab"]',
                        '[role="checkbox"]', '[role="radio"]',
                        '[onclick]', '[tabindex="0"]'
                    ];
                    
                    selectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                const attrs = {};
                                if (el.attributes) {
                                    for (let n = 0; n < el.attributes.length; n++) {
                                        attrs[el.attributes[n].name] = el.attributes[n].value;
                                    }
                                }
                                elements.push({
                                    tag: el.tagName.toLowerCase(),
                                    type: el.type || el.getAttribute('role'),
                                    text: el.innerText?.substring(0, 100) || '',
                                    placeholder: el.placeholder || '',
                                    value: el.value || '',
                                    attributes: attrs,
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
                    
                    return elements.slice(0, 50);
                }
            """)
            
            logger.info(f"[Playwright MCP] 页面分析完成: {page_name or url}")
            
            return {
                "url": url,
                "title": title or page_name,
                "meta_description": meta_description,
                "interactive_elements": interactive_elements,
                "status_code": response.status,
                "load_time": response.headers.get('x-response-time', 'N/A')
            }
            
        except Exception as e:
            logger.error(f"[Playwright MCP] 页面分析失败 {url}: {e}", exc_info=True)
            return None
        finally:
            if page:
                page.close()
    
    async def analyze_page(
        self,
        url: str,
        page_name: str = "",
        timeout: int = 30000
    ) -> Optional[dict[str, Any]]:
        """
        分析单个页面（在独立线程中执行）
        
        参数:
            url: 页面URL
            page_name: 页面名称
            timeout: 超时时间（毫秒）
        
        返回:
            页面分析结果
        """
        import asyncio
        loop = asyncio.get_event_loop()
        
        # 在线程池中执行，但使用run_in_thread确保所有操作在同一线程
        def wrapper():
            return self._run_in_thread(
                self._analyze_page_sync,
                url,
                page_name,
                timeout
            )
        
        return await loop.run_in_executor(None, wrapper)
    
    async def analyze_pages_batch(
        self,
        pages: list[dict],
        project_id: str = "",
        timeout: int = 30000
    ) -> list[dict[str, Any]]:
        """
        批量分析多个页面（逐个执行）
        
        参数:
            pages: 页面列表 [{"url": "...", "name": "..."}]
            project_id: 项目ID
            timeout: 超时时间（毫秒）
        
        返回:
            页面分析结果列表
        """
        results = []
        for page in pages:
            result = await self.analyze_page(
                page["url"],
                page.get("name", ""),
                timeout
            )
            if result:
                results.append(result)
        return results
