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
// 高鲁棒性注入探测器
if (!window._playbotInitialized) {
    window._playbotInitialized = true;
    
    function extractData(el) {
        try {
            const attrs = {};
            if (el && el.attributes) {
                for (let i = 0; i < el.attributes.length; i++) {
                    attrs[el.attributes[i].name] = el.attributes[i].value;
                }
            }
            
            let path = el.tagName ? el.tagName.toLowerCase() : 'unknown';
            let current = el;
            while (current && current.parentElement) {
                current = current.parentElement;
                path = (current.tagName ? current.tagName.toLowerCase() : '') + ' > ' + path;
            }
            
            let componentName = null;
            if (el && el.closest) {
                const compEl = el.closest('[data-playbot-component]');
                if (compEl) {
                    componentName = compEl.getAttribute('data-playbot-component');
                }
            }

            return {
                tag: el.tagName ? el.tagName.toLowerCase() : 'unknown',
                text: ((el.innerText || el.value || '') + '').substring(0, 100),
                attrs: attrs,
                path: path,
                component: componentName,
                url: window.location.href
            };
        } catch (e) {
            return { tag: 'error', text: String(e.message), attrs: {}, path: '', component: null, url: window.location.href };
        }
    }
    
    function showToast(msg, bgColor = '#52c41a') {
        const id = 'playbot-notification-box';
        let el = document.getElementById(id);
        if (el) el.remove();
        el = document.createElement('div');
        el.id = id;
        el.textContent = msg;
        Object.assign(el.style, {
            position: 'fixed', top: '10px', left: '50%', transform: 'translateX(-50%)',
            padding: '10px 24px', backgroundColor: bgColor, color: 'white', borderRadius: '6px',
            zIndex: '2147483647', fontWeight: 'bold', boxShadow: '0 4px 15px rgba(0,0,0,0.3)',
            pointerEvents: 'none', transition: 'opacity 0.4s ease', fontFamily: 'system-ui, sans-serif',
            fontSize: '14px', textAlign: 'center', minWidth: '200px'
        });
        document.documentElement.appendChild(el);
        setTimeout(() => { if (el) { el.style.opacity = '0'; setTimeout(() => { if (el.parentNode) el.remove(); }, 400); } }, 2000);
    }

    // 1. Shadow DOM 穿透的 Click 捕获
    document.addEventListener('click', (e) => {
        try {
            let originalTarget = e.composedPath ? e.composedPath()[0] : e.target;
            let target = originalTarget;
            while (target && target !== document.body && !['button', 'a', 'input'].includes(target.tagName ? target.tagName.toLowerCase() : '') && !(target.getAttribute && target.getAttribute('role')) && !(target.getAttribute && target.getAttribute('data-testid'))) {
                target = target.parentElement;
            }
            if (!target || target === document.body) target = originalTarget;
            
            const data = extractData(target);
            data.action = 'click';
            if (window.playbotRecordAction) {
                showToast('动作已记录: ' + data.action);
                window.playbotRecordAction(data).catch(err => console.error(err));
            }
        } catch(err) {
            if (window.playbotRecordAction) window.playbotRecordAction({action: 'error', error: String(err.message)});
        }
    }, true);
    
    window._playbotInputTimers = window._playbotInputTimers || {};
    
    const handleInputStr = (eTarget) => {
        try {
            if (eTarget && ['input', 'textarea', 'select'].includes(eTarget.tagName ? eTarget.tagName.toLowerCase() : '')) {
                const data = extractData(eTarget);
                data.action = 'input';
                data.value = eTarget.value;
                if (window.playbotRecordAction) {
                    showToast('输入已捕获', '#1890ff');
                    window.playbotRecordAction(data).catch(err => console.error(err));
                }
            }
        } catch(err) {}
    };

    document.addEventListener('input', (e) => {
        const target = e.composedPath ? e.composedPath()[0] : e.target;
        if (!target) return;
        target.dataset.playbotId = target.dataset.playbotId || ('P' + Date.now() + Math.random());
        const id = target.dataset.playbotId;
        clearTimeout(window._playbotInputTimers[id]);
        window._playbotInputTimers[id] = setTimeout(() => { handleInputStr(target); }, 500);
    }, true);
    
    document.addEventListener('change', (e) => {
        const target = e.composedPath ? e.composedPath()[0] : e.target;
        if (target && target.dataset) clearTimeout(window._playbotInputTimers[target.dataset.playbotId]);
        handleInputStr(target);
    }, true);

    // 2. 键盘事件捕获 (Enter / Escape)
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === 'Escape') {
            try {
                let target = e.composedPath ? e.composedPath()[0] : e.target;
                const data = extractData(target);
                data.action = 'keydown';
                data.value = e.key;
                if (window.playbotRecordAction) window.playbotRecordAction(data).catch(err => {});
            } catch(err) {}
        }
    }, true);
    
    // 3. Hover 悬停检测 (防抖)
    let hoverTimer = null;
    document.addEventListener('mouseover', (e) => {
        const target = e.composedPath ? e.composedPath()[0] : e.target;
        if (!target || target === document.body || target === document.documentElement) return;
        clearTimeout(hoverTimer);
        hoverTimer = setTimeout(() => {
            // 降低噪音：只记录带有明确交互意图的标签或者带样式的容器
            if (['button', 'a', 'li'].includes(target.tagName ? target.tagName.toLowerCase() : '') || (target.getAttribute && target.getAttribute('role'))) {
                try {
                    const data = extractData(target);
                    data.action = 'hover';
                    if (window.playbotRecordAction) window.playbotRecordAction(data).catch(err => {});
                } catch(err) {}
            }
        }, 800); // 必须悬停 800ms 且引发重绘
    }, true);
    
    document.addEventListener('mouseout', () => clearTimeout(hoverTimer), true);
    
    // 4. SPA 虚假路由切换拦截 (History API 劫持)
    const originalPushState = history.pushState;
    history.pushState = function() {
        originalPushState.apply(this, arguments);
        if (window.playbotRecordAction) window.playbotRecordAction({action: 'virtual_navigate', url: window.location.href}).catch(err => {});
    };
    
    const originalReplaceState = history.replaceState;
    history.replaceState = function() {
        originalReplaceState.apply(this, arguments);
        if (window.playbotRecordAction) window.playbotRecordAction({action: 'virtual_navigate', url: window.location.href}).catch(err => {});
    };
    
    window.addEventListener('popstate', () => {
        if (window.playbotRecordAction) window.playbotRecordAction({action: 'virtual_navigate', url: window.location.href}).catch(err => {});
    });
    
    // 5. title变化监听
    let oldTitle = document.title;
    const titleObserver = new MutationObserver(() => {
        if (document.title !== oldTitle) {
            oldTitle = document.title;
            if (window.playbotRecordAction) window.playbotRecordAction({action: 'title_changed', value: document.title, url: window.location.href}).catch(err => {});
        }
    });
    // 6. 运行时组件反向扫描 (覆盖率分析)
    function pingComponents() {
        if (!window.playbotRecordAction) return;
        try {
            const comps = Array.from(document.querySelectorAll('[data-playbot-component]'))
                .map(el => el.getAttribute('data-playbot-component'))
                .filter(Boolean);
            const uniqueComps = [...new Set(comps)];
            if (uniqueComps.length > 0) {
                window.playbotRecordAction({
                    action: 'active_components',
                    url: window.location.href,
                    value: uniqueComps
                }).catch(err => {});
            }
        } catch(err) {}
    }
    
    window.addEventListener('load', pingComponents);
    setInterval(pingComponents, 3000);
}
"""

class SelectorGenerator:
    @staticmethod
    def generate_statement(data: dict) -> str:
        action = data.get('action')
        attrs = data.get('attrs', {})
        tag = data.get('tag', '*')
        text = data.get('text', '')
        path = data.get('path', '')
        
        # 对于不依赖 target 的全局操作
        if action == 'virtual_navigate':
            return f"# 页面内部路由跳转: {data.get('url')}"
        if action == 'title_changed':
            return f"# 页面Title更新: {data.get('value')}"
        if action == 'active_components':
            return f"# 刷新活跃组件快照"
            
        selector = ""
        # 1. 优先 data-testid
        if 'data-testid' in attrs:
            selector = f"[data-testid='{attrs['data-testid']}']"
        elif 'id' in attrs and 'el-id' not in attrs['id'] and not any(char.isdigit() for char in attrs['id']):
            selector = f"#{attrs['id']}"
        # 2. name 属性
        elif 'name' in attrs:
            selector = f"{tag}[name='{attrs['name']}']"
        # 3. placeholder 用于 input
        elif 'placeholder' in attrs:
            selector = f"{tag}[placeholder='{attrs['placeholder']}']"
        # 4. text 内容 (对 button / a)
        elif tag in ['button', 'a'] and text and len(text) < 20 and '\n' not in text:
            selector = f"{tag}:has-text('{text}')"
        # 5. Type
        elif tag == 'input' and 'type' in attrs and attrs['type'] not in ['text']:
            selector = f"input[type='{attrs['type']}']"
        # 6. Fallback path
        else:
            selector = path

        selector = selector.replace("'", "\'")
        
        if action == 'click':
            return f"page.locator('{selector}').click()"
        elif action == 'input':
            val = data.get('value', '').replace("'", "\'")
            return f"page.locator('{selector}').fill('{val}')"
        elif action == 'keydown':
            key = data.get('value', '')
            return f"page.locator('{selector}').press('{key}')"
        elif action == 'hover':
            return f"page.locator('{selector}').hover()"
            
        return f"# unknown action {action} on {selector}"


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
        import time
        if not self.start_time:
            self.start_time = time.time()
        if base_url:
            self._browser_base_url = base_url
        logger.info(f"[录制会话] 开始录制: {self.project_id}")
        if not self.browser:
            self.launch_browser()

    def _setup_page_listeners(self, page):
        """设置页面级别的隐性交互和拓扑追踪监听"""
        page.on("dialog", lambda d: self._handle_dialog(d))
        page.on("filechooser", lambda fc: self._handle_filechooser(fc))
        page.on("response", lambda r: self._handle_response(r, page))

    def _handle_dialog(self, dialog):
        import time
        if not hasattr(self, 'action_history'):
            self.action_history = []
        self.action_history.append({
            "time": time.time(),
            "url": dialog.page.url,
            "statement": f"# 处理弹出框: {dialog.type} - {dialog.message}",
            "raw_data": {"action": "handle_dialog", "value": dialog.message, "type": dialog.type}
        })
        try:
            dialog.accept()
        except: pass
        self.save()

    def _handle_filechooser(self, file_chooser):
        import time
        if not hasattr(self, 'action_history'):
            self.action_history = []
        self.action_history.append({
            "time": time.time(),
            "url": file_chooser.page.url,
            "statement": f"# 激活文件选择器",
            "raw_data": {"action": "upload_file"}
        })
        self.save()

    def _handle_response(self, response, page=None):
        if response.request.resource_type in ["xhr", "fetch"]:
            import time
            if not hasattr(self, 'action_history'):
                self.action_history = []
                
            page_url = page.url if page else response.url
            
            self.action_history.append({
                "time": time.time(),
                "url": page_url, 
                "statement": f"# XHR 响应: [{response.request.method}] {response.status} - {response.url}",
                "raw_data": {
                    "action": "network_response",
                    "url": response.url,
                    "status": response.status,
                    "method": response.request.method
                }
            })
            self.save()

    def launch_browser(self):
        """启动录制浏览器线程"""
        if self.browser:
            logger.warning("[录制会话] 浏览器已存在")
            return
            
        self._should_stop = False
            
        def browser_thread():
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    self._playwright = p
                    self.browser = p.chromium.launch(
                        headless=False,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    self.context = self.browser.new_context(
                        viewport={'width': 1280, 'height': 800}
                    )
                    
                    self.context.expose_binding("playbotRecordAction", self._handle_action)
                    self.context.add_init_script(EXTRACT_DOM_JS)
                    self.context.on("page", self._setup_page_listeners)
                    
                    self.page = self.context.new_page()
                    self._setup_page_listeners(self.page)
                    
                    if self._browser_base_url and not self._browser_base_url.startswith(('http://', 'https://')):
                        self._browser_base_url = f"http://{self._browser_base_url}"
                    
                    if self._browser_base_url:
                        try:
                            self.page.goto(self._browser_base_url, wait_until='load', timeout=30000)
                        except Exception as e:
                            print(f"[录制会话]  起始页面加载部分失败: {e}", flush=True)
                    
                    while self.browser and self.context and len(self.context.pages) > 0:
                        if getattr(self, '_should_stop', False):
                            print("[录制会话] 收到停止信号，正在主动退出浏览器线程...", flush=True)
                            break
                        try:
                            if self.page and not self.page.is_closed():
                                self.page.wait_for_timeout(1000)
                            else:
                                import time
                                time.sleep(1)
                        except Exception as e:
                            # 捕获 TargetClosedError 或其他异常
                            break
                            
                    print("[录制会话]  浏览器连接已断开", flush=True)
                    if self.status in ['recording', 'paused']:
                        self.status = 'interrupted'
            except Exception as e:
                print(f"[录制会话]  浏览器线程发生崩溃: {e}", flush=True)
            finally:
                # 必须重置引用，否则下一次 launch_browser 判断 self.browser 为真会直接 return
                self.browser = None
                self.context = None
                self.page = None
                self._playwright = None
                self._browser_thread = None
                
        import threading
        self._browser_thread = threading.Thread(target=browser_thread, daemon=True)
        self._browser_thread.start()

    def save(self):
        import os, json
        os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
        try:
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'status': self.status,
                    'action_history': getattr(self, 'action_history', []),
                    'total_duration': getattr(self, 'total_duration', 0)
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[录制会话] 保存失败: {e}")

    def stop_browser(self):
        self._should_stop = True
        # 不要在主线程中调用 self.browser.close()，这会导致 Playwright 跨线程同步死锁。
        # 设置标识位后，内部循环结束时，with sync_playwright() 上下文管理器会自动析构并安全关闭。

    def pause(self):
        import time
        if self.status == 'recording':
            self.status = 'paused'
            if self.start_time:
                self.total_duration += (time.time() - self.start_time)
                self.start_time = None
            self.save()

    def resume(self):
        import time
        if self.status in ['paused', 'idle', 'interrupted']:
            self.status = 'recording'
            self.start_time = time.time()
            self.save()
            if not self.browser:
                self.launch_browser()

    def stop(self):
        import time
        self.stop_browser()
        if self.status == 'recording' and getattr(self, 'start_time', None):
            self.total_duration += (time.time() - self.start_time)
        self.status = 'completed'
        self.start_time = None
        self.save()

    def _handle_action(self, source, action_data):
        import time
        try:
            print(f"[录制会话] 收到原生请求: {action_data}", flush=True)
            stmt = SelectorGenerator.generate_statement(action_data)
            print(f"[录制会话] 动作捕获: {stmt}", flush=True)
            
            if not hasattr(self, 'action_history'):
                self.action_history = []
                
            self.action_history.append({
                "time": time.time(),
                "url": action_data.get('url') or source['page'].url,
                "statement": stmt,
                "raw_data": action_data,
                "component": action_data.get('component')
            })
            
            # 立即保存状态，防止丢失
            self.save()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[录制会话] 处理动作发生错误: {e}", flush=True)

    def _show_browser_notification(self, message: str, color: str = "#52c41a"):
        """在录制浏览器所有已开页面中显示悬浮提示，保证用户能看到"""
        if not self.context:
            return
        
        script = """
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
        """
        
        try:
            for p in self.context.pages:
                if not p.is_closed():
                    try:
                        p.evaluate(script, [message, color])
                    except:
                        pass
        except Exception as e:
            logger.warning(f"[录制会话] 注入通知失败: {e}")
    
    def _normalize_url(self, url: str) -> str:
        """URL规范化（使用标准库，去参数、兼容 Hash 路由架构）"""
        from urllib.parse import urlparse
        
        # 兼容不带前缀的裸路径
        target_url = url if '://' in url else f"http://{url}"
        parsed = urlparse(target_url)
        
        # 基础路径
        base_path = parsed.path
        if not base_path.startswith('/'):
            base_path = '/' + base_path
            
        # 解析 Hash 路由（适配 SPA）
        hash_route = ''
        if parsed.fragment and '/' in parsed.fragment:
            # 去除 Hash 里的类似查询参数部分 (例如 #/settings?tab=1)
            hash_str = parsed.fragment.split('?')[0]
            hash_route = hash_str if hash_str.startswith('/') else '/' + hash_str
            
        # 组装
        final_route = base_path
        if final_route == '/':
            final_route = ''
        final_route += hash_route
        
        if not final_route:
            final_route = '/'
            
        # 移除末尾斜杠
        if len(final_route) > 1 and final_route.endswith('/'):
            final_route = final_route[:-1]
            
        return final_route
    
    def load(self) -> bool:
        """加载会话"""
        import os, json
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.status = data.get('status', 'idle')
                    self.action_history = data.get('action_history', [])
                    self.total_duration = data.get('total_duration', 0)
                return True
            except Exception as e:
                import logging
                logging.error(f"[录制会话] 加载失败: {e}")
        return False
    
    def clear(self):
        """清空会话"""
        try:
            self.stop_browser()
        except: pass
        import os
        if os.path.exists(self.session_file):
            os.remove(self.session_file)
        self.status = 'idle'
        self.action_history = []
        self.start_time = None
        self.total_duration = 0
        self._browser_base_url = None
    
    def to_dict(self) -> dict:
        """转化为字典"""
        return {
            'project_id': self.project_id,
            'status': self.status,
            'action_count': len(getattr(self, 'action_history', [])),
            'total_duration': getattr(self, 'total_duration', 0)
        }
