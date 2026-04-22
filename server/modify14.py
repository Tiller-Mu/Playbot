import re

with open(r'd:\dpProject\Playbot\server\app\services\recording_session.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_js = """EXTRACT_DOM_JS = \"\"\"
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

            return {
                tag: el.tagName ? el.tagName.toLowerCase() : 'unknown',
                text: ((el.innerText || el.value || '') + '').substring(0, 100),
                attrs: attrs,
                path: path
            };
        } catch (e) {
            return { tag: 'error', text: String(e.message), attrs: {}, path: '' };
        }
    }
    
    document.addEventListener('click', (e) => {
        try {
            let target = e.target;
            while (target && target !== document.body && !['button', 'a', 'input'].includes(target.tagName ? target.tagName.toLowerCase() : '') && !target.getAttribute('role') && !target.getAttribute('data-testid')) {
                target = target.parentElement;
            }
            if (!target) target = e.target;
            
            const data = extractData(target);
            data.action = 'click';
            if (window.playbotRecordAction) {
                window.playbotRecordAction(data).catch(err => console.error(err));
            }
        } catch(err) {
            console.error('Playbot Click Capture Error: ', err);
            if (window.playbotRecordAction) window.playbotRecordAction({action: 'error', error: String(err.message)});
        }
    }, true);
    
    document.addEventListener('change', (e) => {
        try {
            if (e.target && ['input', 'textarea', 'select'].includes(e.target.tagName ? e.target.tagName.toLowerCase() : '')) {
                const data = extractData(e.target);
                data.action = 'input';
                data.value = e.target.value;
                if (window.playbotRecordAction) {
                    window.playbotRecordAction(data).catch(err => console.error(err));
                }
            }
        } catch(err) {}
    }, true);
}
\"\"\""""

text = re.sub(r'EXTRACT_DOM_JS = \"\"\"\n// 注入全局事件侦听器以拦截用户操作.*?\}\n\"\"\"', new_js, text, flags=re.DOTALL)

# Add try-except to _handle_action
handle_action = """    def _handle_action(self, source, action_data):
        import time
        try:
            print(f"[录制会话] 收到原生请求: {action_data}", flush=True)
            stmt = SelectorGenerator.generate_statement(action_data)
            print(f"[录制会话] 🎯 动作捕获: {stmt}", flush=True)
            
            if not hasattr(self, 'action_history'):
                self.action_history = []
                
            self.action_history.append({
                "time": time.time(),
                "url": source['page'].url,
                "statement": stmt,
                "raw_data": action_data
            })
            
            self._show_browser_notification(f"动作已记录", color="#52c41a")
        except Exception as e:
            print(f"[录制会话] 处理动作发生错误: {e}", flush=True)"""

text = re.sub(r'    def _handle_action\(self, source, action_data\):.*?            self._show_browser_notification\(f"已记录\w*: \{stmt\}", color="#52c41a"\)', handle_action, text, flags=re.DOTALL)
# One more fallback for older regex replacement:
if 'def _handle_action(self, source, action_data):' in text and '[录制会话] 收到原生请求' not in text:
    text = re.sub(r'    def _handle_action\(self, source, action_data\):.*?            self._show_browser_notification\([^)]+\)', handle_action, text, flags=re.DOTALL)


with open(r'd:\dpProject\Playbot\server\app\services\recording_session.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Robust JS applied!')
