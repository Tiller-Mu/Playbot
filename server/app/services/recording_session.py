"""录制会话管理 - 支持暂停/继续、自动去重、会话持久化、浏览器控制"""
import os
import re
import json
import time
import logging
import threading
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class RecordingSession:
    """录制会话状态管理"""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.status = 'idle'  # idle | recording | paused | completed
        self.discovered_pages = {}  # {route_pattern: {urls: [], dom: None, components: []}}
        self.start_time = None
        self.total_duration = 0
        self.session_file = f"workspace/sessions/{project_id}.json"
        
        # 浏览器相关
        self._playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._browser_thread: Optional[threading.Thread] = None
        self._browser_base_url = None
    
    def start(self, base_url: str = None):
        """开始/继续录制"""
        self.status = 'recording'
        if not self.start_time:
            self.start_time = time.time()
        if base_url:
            self._browser_base_url = base_url
        logger.info(f"[录制会话] 开始录制: {self.project_id}")
    
    def launch_browser(self):
        """在独立线程中启动浏览器窗口"""
        if self.browser:
            logger.warning("[录制会话] 浏览器已存在")
            return
        
        def browser_thread():
            try:
                logger.info("[录制会话] 🚀 启动浏览器...")
                self._playwright = sync_playwright().start()
                
                # 启动可见的浏览器窗口（非headless）
                self.browser = self._playwright.chromium.launch(
                    headless=False,  # 显示浏览器窗口
                    args=[
                        '--no-sandbox',
                        '--start-maximized',  # 启动时最大化
                        '--window-size=1920,1080'  # 窗口尺寸
                    ]
                )
                
                logger.info("[录制会话] ✅ 浏览器进程启动成功")
                
                # 创建浏览器上下文（不设置固定viewport，使用浏览器窗口大小）
                self.context = self.browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport=None,  # 不使用固定viewport，让页面自适应窗口
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai'
                )
                
                # 创建页面
                self.page = self.context.new_page()
                logger.info("[录制会话] ✅ 浏览器页面创建成功")
                
                # 监听导航事件
                self.page.on('framenavigated', self._on_navigation)
                
                # 打开起始页面
                if self._browser_base_url:
                    logger.info(f"[录制会话] 🌐 访问起始页面: {self._browser_base_url}")
                    try:
                        # 使用domcontentloaded更快启动
                        self.page.goto(
                            self._browser_base_url, 
                            wait_until='domcontentloaded',
                            timeout=30000
                        )
                        logger.info(f"[录制会话] ✅ 起始页面加载完成")
                    except Exception as e:
                        logger.warning(f"[录制会话] ⚠️ 起始页面加载超时或失败: {e}")
                        # 继续执行，不阻塞录制
                
                logger.info("[录制会话] ✅ 浏览器启动成功，等待用户操作...")
                logger.info("[录制会话] 💡 提示：请在打开的浏览器窗口中访问页面，系统会自动记录")
                
                # 保持浏览器线程运行
                import time
                while self.browser and not self.browser.is_closed():
                    time.sleep(1)
                
                logger.info("[录制会话] 浏览器窗口已关闭")
                
            except Exception as e:
                logger.error(f"[录制会话] ❌ 浏览器启动失败: {e}", exc_info=True)
        
        self._browser_thread = threading.Thread(target=browser_thread, daemon=True)
        self._browser_thread.start()
        
        # 等待浏览器启动
        time.sleep(3)
    
    def _on_navigation(self, frame):
        """页面导航回调 - 在浏览器线程中直接捕获DOM"""
        if self.status != 'recording':
            return
        
        url = frame.url
        
        # 过滤非HTTP URL（如about:blank）
        if not url.startswith('http'):
            return
        
        logger.info(f"[录制会话] 📍 页面导航: {url}")
        
        # 直接在浏览器线程中捕获DOM（避免跨线程问题）
        try:
            # 等待页面加载（使用较短的超时）
            try:
                self.page.wait_for_load_state('domcontentloaded', timeout=5000)
            except:
                pass  # 如果已经加载完成，忽略超时
            
            # 额外等待资源加载
            import time
            time.sleep(0.3)
            
            # 获取DOM
            dom = self.page.evaluate('() => document.documentElement.outerHTML')
            
            if dom and len(dom) > 100:  # 确保DOM不为空
                self.add_page(url, {'html': dom, 'url': url})
                logger.info(f"[录制会话] ✅ DOM捕获成功: {len(dom)} 字符, URL: {url}")
            else:
                logger.warning(f"[录制会话] ⚠️ DOM为空或太短: {url}")
        except Exception as e:
            logger.error(f"[录制会话] ❌ DOM捕获失败 {url}: {e}")
    
    def stop_browser(self):
        """关闭浏览器"""
        try:
            if self.page:
                self.page.close()
                self.page = None
            if self.browser:
                self.browser.close()
                self.browser = None
            if self._playwright:
                # Playwright必须在同一个线程中停止
                self._playwright.stop()
                self._playwright = None
            logger.info("[录制会话] 浏览器已关闭")
        except Exception as e:
            # 浏览器可能已经在其他线程关闭，忽略错误
            logger.debug(f"[录制会话] 关闭浏览器（已忽略）: {e}")
            self.page = None
            self.browser = None
            self._playwright = None
    
    def pause(self):
        """暂停录制"""
        if self.status == 'recording':
            self.status = 'paused'
            if self.start_time:
                self.total_duration += (time.time() - self.start_time)
                self.start_time = None
            self._save()  # 自动保存
            logger.info(f"[录制会话] 暂停录制: {self.project_id}")
            # 不关闭浏览器，保持页面状态
    
    def resume(self):
        """继续录制"""
        if self.status == 'paused':
            self.status = 'recording'
            self.start_time = time.time()
            logger.info(f"[录制会话] 继续录制: {self.project_id}")
    
    def stop(self):
        """停止录制"""
        self.status = 'completed'
        if self.start_time:
            self.total_duration += (time.time() - self.start_time)
            self.start_time = None
        self._save()
        
        # 关闭浏览器
        self.stop_browser()
        
        logger.info(f"[录制会话] 停止录制: {self.project_id}, 总时长: {self.total_duration:.1f}秒")
    
    def add_page(self, url: str, dom_data: dict):
        """添加页面（自动去重）"""
        route_pattern = self._normalize_url(url)
        
        if route_pattern not in self.discovered_pages:
            self.discovered_pages[route_pattern] = {
                'pattern': route_pattern,
                'urls': [],
                'dom': dom_data,
                'components': [],
                'first_visit': time.time()
            }
            logger.info(f"[录制会话] 发现新页面: {route_pattern}")
        else:
            # 去重：只记录一次DOM
            if self.discovered_pages[route_pattern]['dom'] is None:
                self.discovered_pages[route_pattern]['dom'] = dom_data
            logger.debug(f"[录制会话] 重复访问页面: {route_pattern}")
        
        # 记录访问历史
        self.discovered_pages[route_pattern]['urls'].append(url)
    
    def _normalize_url(self, url: str) -> str:
        """URL规范化（去参数、替换ID）"""
        # 移除协议和域名，只保留路径
        if '://' in url:
            url = url.split('://', 1)[1]
            url = url.split('/', 1)[1] if '/' in url else ''
            url = '/' + url
        
        # 移除查询参数
        url = url.split('?')[0]
        
        # 移除哈希
        url = url.split('#')[0]
        
        # 替换数字ID为:id
        url = re.sub(r'/\d+', '/:id', url)
        
        # 替换UUID为:id
        uuid_pattern = r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        url = re.sub(uuid_pattern, '/:id', url, flags=re.IGNORECASE)
        
        # 确保以/开头
        if not url.startswith('/'):
            url = '/' + url
        
        return url
    
    def load(self) -> bool:
        """加载会话"""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.status = data.get('status', 'idle')
                    self.discovered_pages = data.get('discovered_pages', {})
                    self.total_duration = data.get('total_duration', 0)
                logger.info(f"[录制会话] 加载会话: {self.project_id}, 已发现 {len(self.discovered_pages)} 个页面")
                return True
            except Exception as e:
                logger.error(f"[录制会话] 加载会话失败: {e}")
        return False
    
    def _save(self):
        """保存会话到文件"""
        try:
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            data = {
                'project_id': self.project_id,
                'status': self.status,
                'discovered_pages': self.discovered_pages,
                'total_duration': self.total_duration
            }
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[录制会话] 保存会话: {self.project_id}")
        except Exception as e:
            logger.error(f"[录制会话] 保存会话失败: {e}")
    
    def clear(self):
        """清除会话"""
        # 先关闭浏览器
        self.stop_browser()
        
        if os.path.exists(self.session_file):
            os.remove(self.session_file)
        self.status = 'idle'
        self.discovered_pages = {}
        self.start_time = None
        self.total_duration = 0
        self._browser_base_url = None
        logger.info(f"[录制会话] 清除会话: {self.project_id}")
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'project_id': self.project_id,
            'status': self.status,
            'discovered_pages': self.discovered_pages,
            'total_duration': self.total_duration
        }
