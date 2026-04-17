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


# 全局注入的高级 DOM 结构化提取器（完全兼容后端的智能模型节点）
EXTRACT_DOM_JS = """
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
                elements.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || el.getAttribute('role') || '',
                    id: el.id || '',
                    class: typeof el.className === 'string' ? el.className : '',
                    text: (el.innerText || '').substring(0, 100),
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                    selector: `${el.tagName.toLowerCase()}${el.id ? '#'+el.id : ''}${typeof el.className === 'string' && el.className ? '.'+el.className.trim().replace(/\s+/g, '.') : ''}`
                });
            }
        });
    });
    
    return {
        html: document.documentElement.outerHTML,
        interactive_elements: elements
    };
}
"""

class RecordingSession:
    """录制会话状态管理"""
    
    def __init__(self, project_id: str):
        print(f"[录制会话] 实例化新的会话对象: {project_id}", flush=True)
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
                print(f"[录制会话] 🚀 准备启动浏览器线程: {self.project_id}", flush=True)
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
                
                print("[录制会话] ✅ 浏览器进程已启动", flush=True)
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
                print("[录制会话] ✅ 浏览器页面已创建", flush=True)
                logger.info("[录制会话] ✅ 浏览器页面创建成功")
                
                # 监听导航事件
                self.page.on('framenavigated', self._on_navigation)
                
                # 监听URL变化（支持SPA前端路由）
                self.page.on('load', self._on_page_load)
                
                print("[录制会话] 📡 已注册页面导航监听器", flush=True)
                logger.info("[录制会话] 已注册页面导航监听器（支持SPA）")
                
                # 确保 base_url 有协议头
                if self._browser_base_url and not self._browser_base_url.startswith(('http://', 'https://')):
                    self._browser_base_url = f"http://{self._browser_base_url}"
                
                # 打开起始页面
                if self._browser_base_url:
                    print(f"[录制会话] 🌐 正在访问起始页面: {self._browser_base_url}", flush=True)
                    logger.info(f"[录制会话] 🌐 访问起始页面: {self._browser_base_url}")
                    try:
                        # 使用domcontentloaded更快启动
                        self.page.goto(
                            self._browser_base_url, 
                            wait_until='load',  # 改为 load 确保页面更完整
                            timeout=30000
                        )
                        print(f"[录制会话] ✅ 起始页面已加载", flush=True)
                        logger.info(f"[录制会话] ✅ 起始页面加载完成")
                    except Exception as e:
                        print(f"[录制会话] ⚠️ 起始页面加载超时或失败: {e}", flush=True)
                        logger.warning(f"[录制会话] ⚠️ 起始页面加载超时或失败: {e}")
                
                print("[录制会话] ✅ 浏览器就绪，进入主动监控循环...", flush=True)
                
                # 记录上次捕获的 DOM 长度，用于支持 Tab/Modal 变化
                last_dom_fingerprint = {} # {url: length}
                
                while self.browser and self.browser.is_connected():
                    try:
                        # 遍历所有打开的页面（支持多标签页）
                        pages = [p for p in self.context.pages if not p.is_closed()]
                        for p in pages:
                            current_url = p.url
                            if not current_url.startswith('http'):
                                continue
                                
                            route_pattern = self._normalize_url(current_url)
                            
                            # 触发捕获的两个条件：
                            # 1. URL 发生了变化
                            # 2. 页面内容发生了重大变化 (即使 URL 没变)
                            try:
                                # 只有当页面处于 idle 状态且可交互时才抓取，避免频繁 evaluate 导致的性能问题
                                # 我们这里直接尝试抓取长度
                                dom_len = p.evaluate('() => document.documentElement.outerHTML.length')
                                
                                is_new_url = current_url != last_url
                                old_len = last_dom_fingerprint.get(current_url, 0)
                                is_content_changed = abs(dom_len - old_len) > 500
                                
                                if is_new_url or is_content_changed:
                                    # 更新当前的活跃页面对象供其他方法使用
                                    self.page = p
                                    
                                    if is_new_url:
                                        print(f"[录制会话] 🚀 路径切换: {current_url}", flush=True)
                                        last_url = current_url
                                    
                                    # 抓取并保存
                                    self._check_and_capture(current_url)
                                    last_dom_fingerprint[current_url] = dom_len
                            except:
                                continue
                                
                    except Exception:
                        pass
                    
                    time.sleep(0.5) # 稍微放慢轮询，减轻 CPU 压力
                
                print("[录制会话] 🔴 浏览器连接已断开", flush=True)
                logger.info("[录制会话] 浏览器窗口已关闭")
                
            except Exception as e:
                print(f"[录制会话] ❌ 浏览器线程发生崩溃: {e}", flush=True)
                import traceback
                traceback.print_exc()
                logger.error(f"[录制会话] ❌ 浏览器启动失败: {e}", exc_info=True)
        
        self._browser_thread = threading.Thread(target=browser_thread, daemon=True)
        self._browser_thread.start()
        
        # 移除了主线程的 time.sleep(3)，防止 API 挂起
        print(f"[录制会话] 线程已启动，API 准备返回", flush=True)
    
    def _check_and_capture(self, url: str):
        """检查并捕获当前页面（带简单的去重逻辑，避免过度 evaluate）"""
        # 规范化 URL
        route_pattern = self._normalize_url(url)
        
        # 如果是新路由，或者是虽然记录过但还没抓取过 DOM 的路由
        if route_pattern not in self.discovered_pages or self.discovered_pages[route_pattern]['dom'] is None:
            try:
                # 稍微等待稳定
                import time
                time.sleep(0.5)
                
                page_data = self.page.evaluate(EXTRACT_DOM_JS)
                if page_data and page_data.get('html') and len(page_data['html']) > 100:
                    self.add_page(url, {
                        'html': page_data['html'],
                        'interactive_elements': page_data.get('interactive_elements', []),
                        'url': url
                    })
                    print(f"[录制会话] 🤖 自动捕获成功: {route_pattern}", flush=True)
            except:
                pass

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
            
            # 获取结构化DOM数据
            page_data = self.page.evaluate(EXTRACT_DOM_JS)
            
            if page_data and page_data.get('html') and len(page_data['html']) > 100:
                self.add_page(url, {
                    'html': page_data['html'],
                    'interactive_elements': page_data.get('interactive_elements', []),
                    'url': url
                })
                logger.info(f"[录制会话] ✅ DOM捕获成功: {len(page_data['html'])} 字符, URL: {url}")
            else:
                logger.warning(f"[录制会话] ⚠️ DOM为空或太短: {url}")
        except Exception as e:
            logger.error(f"[录制会话] ❌ DOM捕获失败 {url}: {e}")
    
    def _on_page_load(self, page):
        """页面加载完成回调（用于SPA）"""
        if self.status != 'recording':
            return
        
        try:
            url = page.url
            
            # 过滤非HTTP URL
            if not url.startswith('http'):
                return
            
            logger.info(f"[录制会话] 📄 页面加载: {url}")
            
            # 等待并捕获结构化DOM
            import time
            time.sleep(0.5)
            
            page_data = self.page.evaluate(EXTRACT_DOM_JS)
            
            if page_data and page_data.get('html') and len(page_data['html']) > 100:
                self.add_page(url, {
                    'html': page_data['html'],
                    'interactive_elements': page_data.get('interactive_elements', []),
                    'url': url
                })
                logger.info(f"[录制会话] ✅ DOM捕获成功: {len(page_data['html'])} 字符, URL: {url}")
        except Exception as e:
            logger.error(f"[录制会话] ❌ 页面加载捕获失败: {e}")
    
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
        
        # 保存最终状态
        self._save()
        
        # 关闭浏览器
        self.stop_browser()
        
        logger.info(f"[录制会话] 停止录制: {self.project_id}, 总时长: {self.total_duration:.1f}秒")
    
    def add_page(self, url: str, dom_data: dict):
        """添加页面（自动去重与智能更新）"""
        route_pattern = self._normalize_url(url)
        new_dom_len = len(dom_data.get('html', ''))
        
        if route_pattern not in self.discovered_pages:
            # 1. 发现新页面
            self.discovered_pages[route_pattern] = {
                'pattern': route_pattern,
                'urls': [],
                'dom': dom_data,
                'components': [],
                'first_visit': time.time(),
                'last_dom_len': new_dom_len
            }
            print(f"[录制会话] ✨ 发现并保存新页面: {route_pattern}", flush=True)
            self._save()
            self._show_browser_notification(f"✨ 发现新页面: {route_pattern}")
        else:
            # 2. 路径已存在，检查是否需要更新 DOM (例如点开了 Tab 或弹窗)
            old_page = self.discovered_pages[route_pattern]
            old_dom_len = old_page.get('last_dom_len', 0)
            
            # 如果新抓取的 DOM 长度显著增加（比如点开了内容），或者之前没抓到 DOM
            if old_page['dom'] is None or new_dom_len > (old_dom_len + 500):
                old_page['dom'] = dom_data
                old_page['last_dom_len'] = new_dom_len
                self._save()
                print(f"[录制会话] 🔄 更新页面快照 (检测到新内容): {route_pattern}", flush=True)
                self._show_browser_notification(f"✅ 页面快照已更新 (捕获到新交互内容)")
            else:
                logger.debug(f"[录制会话] 重复访问且内容无显著变化: {route_pattern}")
        
        # 记录访问历史
        self.discovered_pages[route_pattern]['urls'].append(url)

    def _show_browser_notification(self, message: str, color: str = "#52c41a"):
        """在录制浏览器中显示一个高度兼容的悬浮提示"""
        if not self.page:
            return
        try:
            # 修正：Playwright evaluate 只接受一个参数，我们将参数打包成列表
            self.page.evaluate("""
                (args) => {
                    const msg = args[0];
                    const bgColor = args[1];
                    console.log('[Playbot] ' + msg);
                    const id = 'playbot-notification-box';
                    let el = document.getElementById(id);
                    if (el) el.remove();
                    
                    el = document.createElement('div');
                    el.id = id;
                    el.textContent = msg;
                    
                    // 极致稳健的样式设置
                    Object.assign(el.style, {
                        position: 'fixed',
                        top: '10px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        padding: '10px 24px',
                        backgroundColor: bgColor,
                        color: 'white',
                        borderRadius: '6px',
                        zIndex: '2147483647',
                        fontWeight: 'bold',
                        boxShadow: '0 4px 15px rgba(0,0,0,0.3)',
                        pointerEvents: 'none',
                        transition: 'opacity 0.4s ease',
                        fontFamily: 'system-ui, -apple-system, sans-serif',
                        fontSize: '15px',
                        lineHeight: '1.4',
                        textAlign: 'center',
                        minWidth: '250px'
                    });
                    
                    document.documentElement.appendChild(el);
                    
                    setTimeout(() => {
                        if (el) {
                            el.style.opacity = '0';
                            setTimeout(() => { if (el && el.parentNode) el.remove(); }, 400);
                        }
                    }, 2500);
                }
            """, [message, color]) # 参数打包
        except Exception as e:
            # 记录错误但不中断流程
            logger.warning(f"[录制会话] 注入通知失败: {e}")
    
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
        
        # 暂时关闭激进的 ID 转换，以观察真实路径匹配情况
        # url = re.sub(r'/\d+', '/:id', url)
        # uuid_pattern = r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        # url = re.sub(uuid_pattern, '/:id', url, flags=re.IGNORECASE)

        # 确保以/开头
        if not url.startswith('/'):
            url = '/' + url

            
        # 移除末尾斜杠（如果是根路径 / 则保留）
        if len(url) > 1 and url.endswith('/'):
            url = url[:-1]
        
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
