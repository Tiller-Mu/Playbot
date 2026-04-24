import logging
import time
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, Locator
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ResolveError(Exception):
    def __init__(self, step: dict, message: str):
        self.step = step
        self.message = message
        super().__init__(self.message)

class PlaybotExecutionEngine:
    def __init__(self, page: Page):
        self.page = page

    def execute_plan(self, steps: List[dict]):
        for step_data in steps:
            step = step_data if isinstance(step_data, dict) else dict(step_data)
            
            logger.info(f"Executing step: {step.get('action')} - {step.get('intent_reason')}")
            
            start_resolve = time.time()
            locator = self._resolve_locator(step)
            resolve_time = time.time() - start_resolve
            logger.info(f"[Timer] _resolve_locator took {resolve_time:.2f} seconds")
            
            if locator is None and step.get("action") not in ["navigate", "custom_script"]:
                snapshot = "Could not capture snapshot"
                if step.get("action") == "expect_visible":
                    raise AssertionError(f"UI 断言失败：预期的元素（{step.get('intent_reason', '未知')}）在超时时间内未出现。\n寻址目标: {step.get('target_hint')}")
                else:
                    raise ResolveError(step, f"UI 寻址失败：无法找到操作目标（{step.get('intent_reason', '未知')}）。\n寻址目标: {step.get('target_hint')}")
                
            start_exec = time.time()
            self._execute_action(locator, step)
            exec_time = time.time() - start_exec
            logger.info(f"[Timer] _execute_action took {exec_time:.2f} seconds")
            
            self._post_validate(step)

    def _get_scopes(self, step: dict) -> List[Locator]:
        scopes = []
        target_component = step.get("target_component")
        
        # 1. 组件沙盒（最高优先级）
        if target_component:
            scopes.append(
                self.page.locator(f'[data-playbot-component="{target_component}"]')
            )

        # 2. 结构沙盒作为回退
        scopes.extend([
            self.page.locator("form"),
            self.page.locator("main"),
            self.page.locator("body")
        ])

        return scopes

    def _collect_candidates(self, scope: Locator, step: dict) -> List[dict]:
        target_hint = step.get("target_hint", {})
        if not target_hint:
            return []

        tag = target_hint.get("tag") or "*"
        hint_text = target_hint.get("text") or ""
        hint_role = target_hint.get("role") or ""
        hint_placeholder = target_hint.get("placeholder") or ""
        
        # 处理单引号防止 JS 报错
        hint_text_js = hint_text.replace("'", "\\'")
        
        try:
            candidates_data = scope.evaluate(f'''(scopeNode) => {{
                const elements = Array.from(scopeNode.querySelectorAll('{tag}'));
                const hintText = '{hint_text_js}';
                const hintRole = '{hint_role}';
                const hintPlaceholder = '{hint_placeholder}';
                
                let results = [];
                const hasHint = hintText || hintRole || hintPlaceholder;
                
                for (let i = 0; i < elements.length; i++) {{
                    let el = elements[i];
                    let elText = el.textContent || el.value || '';
                    
                    // 恢复“软打分”的预过滤：只要命中了任何一个线索，就放进候选池，交给 Python 去精细打分
                    let isMatch = false;
                    if (hintText && elText.includes(hintText)) isMatch = true;
                    if (hintRole && el.getAttribute('role') === hintRole) isMatch = true;
                    if (hintPlaceholder && el.getAttribute('placeholder') === hintPlaceholder) isMatch = true;
                    
                    if (hasHint && !isMatch) {{
                        continue;
                    }}
                    
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                    
                    results.push({{
                        index: i,
                        text: elText,
                        visible: visible,
                        role: el.getAttribute('role') || null,
                        placeholder: el.getAttribute('placeholder') || null
                    }});
                    
                    if (results.length >= 50) break;
                }}
                return results;
            }}''', timeout=500)
        except Exception as e:
            logger.debug(f"Failed to batch extract candidate info: {e}")
            return []

        candidates = []
        for data in candidates_data:
            data["locator"] = scope.locator(tag).nth(data["index"])
            candidates.append(data)

        return candidates

    def _score(self, candidate: dict, step: dict) -> float:
        score = 0.0
        hint = step.get("target_hint", {})

        # 1. 文本匹配（最重要）
        hint_text = hint.get("text")
        if hint_text and candidate.get("text"):
            hint_text = hint_text.strip()
            cand_text = candidate["text"].strip()
            if hint_text in cand_text:
                score += 5.0
                # 如果完全相等，给予绝对高分（防止选中包含该文本的父容器）
                if hint_text == cand_text:
                    score += 5.0
                else:
                    # 根据多余文本的长度进行惩罚，多余字符越多，扣分越多（最多扣4分）
                    length_diff = len(cand_text) - len(hint_text)
                    score -= min(4.0, length_diff * 0.05)

        # 2. role 匹配
        hint_role = hint.get("role")
        if hint_role and candidate.get("role") == hint_role:
            score += 3

        # 3. placeholder 匹配
        hint_placeholder = hint.get("placeholder")
        if hint_placeholder and candidate.get("placeholder") == hint_placeholder:
            score += 2

        # 4. 可见性
        if candidate.get("visible"):
            score += 2

        return score

    def _pick_best(self, candidates: List[dict], step: dict) -> Optional[dict]:
        scored = [
            (self._score(c, step), c)
            for c in candidates
        ]
        
        # 过滤掉得分为0的候选（完全不匹配）
        scored = [item for item in scored if item[0] > 0]

        if not scored:
            return None

        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[0][1]

    def _validate(self, locator: Locator) -> bool:
        try:
            return locator.count() == 1 and locator.is_visible()
        except:
            return False

    def _fallback(self, step: dict) -> Optional[Locator]:
        hint = step.get("target_hint", {})
        if not hint:
            return None
            
        timeout_sec = 15.0 if step.get("action") == "expect_visible" else 5.0
        start_time = time.time()
        
        candidates = []
        if hint.get("text"):
            candidates.append(("exact text", self.page.get_by_text(hint["text"], exact=True)))
            candidates.append(("fuzzy text", self.page.get_by_text(hint["text"], exact=False)))
            
        if hint.get("role"):
            name_arg = hint.get("text")
            if name_arg:
                candidates.append(("role with name", self.page.get_by_role(hint["role"], name=name_arg)))
            candidates.append(("pure role", self.page.get_by_role(hint["role"])))
            
        if hint.get("recorded_selector"):
            selector = hint["recorded_selector"]
            if selector.count("> div") < 5:
                candidates.append(("recorded_selector", self.page.locator(selector)))

        while time.time() - start_time < timeout_sec:
            for strategy, loc in candidates:
                try:
                    if loc.count() > 0:
                        logger.info(f"Fallback succeeded using {strategy}")
                        return loc.first
                except Exception:
                    pass
            time.sleep(0.5)
            
        return None

    def _resolve_locator(self, step: dict) -> Optional[Locator]:
        # 对于不需要目标的操作，直接返回 None
        if step.get("action") in ["navigate", "custom_script"]:
            return None
            
        scopes = self._get_scopes(step)
        
        all_candidates_info = []

        for scope in scopes:
            candidates = self._collect_candidates(scope, step)
            
            if not candidates:
                continue

            best = self._pick_best(candidates, step)
            
            if best:
                all_candidates_info.append(best)
                if self._validate(best["locator"]):
                    self._log_step(step, candidates, best)
                    return best["locator"]

        # 如果都没通过 validate，记录日志并尝试 Fallback
        self._log_step(step, all_candidates_info, None)
        logger.warning(f"Failed to resolve strict locator for step {step.get('action')}, triggering fallback.")
        return self._fallback(step)

    def _execute_action(self, locator: Optional[Locator], step: dict):
        action = step.get("action")
        value = step.get("value")

        if action == "navigate":
            if value:
                try:
                    self.page.goto(value, wait_until="domcontentloaded", timeout=15000)
                except Exception as e:
                    logger.warning(f"Navigation to {value} timed out or failed: {e}")
        elif action == "click":
            locator.click(force=True)
        elif action == "fill":
            locator.fill(value or "", force=True)
        elif action == "select":
            locator.select_option(value, force=True)
        elif action == "check":
            locator.check(force=True)
        elif action == "uncheck":
            locator.uncheck(force=True)
        elif action == "hover":
            locator.hover(force=True)
        elif action == "press":
            locator.press(value)
        elif action == "expect_visible":
            from playwright.sync_api import expect
            expect(locator).to_be_visible()
        elif action == "expect_hidden":
            from playwright.sync_api import expect
            expect(locator).to_be_hidden()
        elif action == "expect_text":
            from playwright.sync_api import expect
            tag = ""
            try:
                tag = locator.evaluate("el => el.tagName.toLowerCase()")
            except Exception:
                pass
                
            if tag in ["input", "textarea", "select"]:
                expect(locator).to_have_value(value or "")
            else:
                expect(locator).to_have_text(value or "")

    def _post_validate(self, step: dict):
        action = step.get("action")
        
        # 简单等待策略，留待后续演进
        if action == "click":
            self.page.wait_for_timeout(300)
            
        # 预留可扩展的空间：
        # - URL 变化等待
        # - DOM 稳定等待
        # - Toast 出现等待

    def _log_step(self, step: dict, candidates: list, chosen: Optional[dict]):
        logger.info(f"[Execution Engine] Step: {step.get('action')}, Target Hint: {step.get('target_hint')}")
        logger.info(f"  -> Found {len(candidates)} candidates.")
        if chosen:
            logger.info(f"  -> Chosen element text: '{chosen.get('text')}', role: {chosen.get('role')}")
        else:
            logger.info("  -> No valid candidate chosen in strict scopes.")
