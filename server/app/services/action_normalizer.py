import logging
from typing import List, Dict, Any
from app.models.semantic_ir import SemanticAction, ActionType, TargetElement

log = logging.getLogger(__name__)

class ActionNormalizer:
    @staticmethod
    def normalize(actions: list[dict]) -> List[SemanticAction]:
        """
        Takes raw action_history items and returns a list of SemanticActions.
        """
        raw_steps = []
        network_events = []
        
        # 1. 基础分发与第一轮分类提取
        i = 0
        while i < len(actions):
            act = actions[i]
            raw = act.get('raw_data', {})
            act_type = raw.get('action') 
            url = act.get('url') or raw.get('url', '')
            
            # 分离出网络事件池（不独立成步骤，稍后挂载到关联动作上）
            if act_type == 'network_response':
                network_events.append({
                    "time": act.get("time", 0),
                    "data": {
                        "request": raw.get("url"),
                        "method": raw.get("method"),
                        "status": raw.get("status")
                    }
                })
                i += 1
                continue
                
            target = TargetElement(
                tag=raw.get('tag', 'unknown'),
                attributes=raw.get('attrs', {}),
                text=raw.get('text', ''),
                component=raw.get('component'),
                path=raw.get('path', '')
            )
            
            if act_type == 'input':
                final_val = raw.get('value', '')
                j = i + 1
                while j < len(actions):
                    next_act = actions[j]
                    if next_act.get('raw_data', {}).get('action') == 'input' and next_act.get('raw_data', {}).get('path') == raw.get('path'):
                        final_val = next_act.get('raw_data', {}).get('value', '')
                        j += 1
                    else: break
                raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.FILL, target=target, url=url, value=final_val)))
                i = j - 1
                
            elif act_type == 'click':
                # 去重点击
                j = i + 1
                while j < len(actions) and actions[j].get('raw_data', {}).get('action') == 'click' and actions[j].get('raw_data', {}).get('path') == raw.get('path'):
                    j += 1
                raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.CLICK, target=target, url=url)))
                i = j - 1
                
            elif act_type == 'keydown':
                if raw.get('value') == 'Enter':
                    # 提纯出表单提交的意图
                    raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.SUBMIT_FORM, target=target, url=url)))
                
            elif act_type == 'hover':
                raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.HOVER, target=target, url=url)))
                
            elif act_type == 'virtual_navigate':
                raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.VIRTUAL_NAVIGATE, url=url)))
                
            elif act_type == 'title_changed':
                raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.SWITCH_VIEW, url=url, value=raw.get('value'))))
                
            elif act_type == 'handle_dialog':
                raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.HANDLE_DIALOG, url=url, value=raw.get('value'), target=TargetElement(tag='dialog', attributes={'type': raw.get('type')}, text=raw.get('value')))))
                
            elif act_type == 'upload_file':
                raw_steps.append((act.get('time', 0), SemanticAction(action=ActionType.UPLOAD_FILE, url=url)))
                
            i += 1

        # 2. 复合动作推断 (Complex Component Inference) - 例如将连贯的 Click 折叠为 Select
        refined_steps = []
        i = 0
        while i < len(raw_steps):
            t1, step = raw_steps[i]
            if step.action == ActionType.CLICK:
                # 检查后面一小堆时间内是否有另一个点击
                j = i + 1
                found_composite = False
                while j < len(raw_steps) and j < i + 3:
                    t2, next_step = raw_steps[j]
                    if next_step.action == ActionType.CLICK and (t2 - t1) < 2.5: # 2.5秒内的二次点击
                        # 判断是否是从父容器点击菜单项 (典型的下拉框 / Popup)
                        is_portal = next_step.target and ('li' in next_step.target.tag or 'option' in next_step.target.tag or 'menu' in next_step.target.path)
                        is_combobox = step.target and ('role' in step.target.attributes and step.target.attributes['role'] in ['combobox', 'button'])
                        
                        if is_portal or is_combobox:
                            # 折叠为 SELECT
                            step.action = ActionType.SELECT
                            step.value = next_step.target.text if next_step.target else ""
                            i = j # 吞并第二个点击
                            found_composite = True
                            break
                    j += 1
            refined_steps.append((t1, step))
            i += 1
            
        # 3. 挂载网络关联 (Network Topology Binding) & 导航计算
        final_steps = []
        last_url = None
        for timestamp, step in refined_steps:
            # Inject native navigation
            if step.url and step.url != last_url and step.action not in [ActionType.VIRTUAL_NAVIGATE, ActionType.SWITCH_VIEW]:
                final_steps.append(SemanticAction(action=ActionType.NAVIGATE, url=step.url))
                last_url = step.url
                
            if step.action in [ActionType.VIRTUAL_NAVIGATE, ActionType.SWITCH_VIEW]:
                last_url = step.url

            # 寻找动作后 1.5 秒内发生的网络请求，挂靠为 action 的 consequence
            relevant_networks = [n for n in network_events if timestamp < n["time"] <= timestamp + 1.5]
            if relevant_networks:
                # 取最有代表性的一个（通常是最早触发或者耗时最久的，此处简单取第一个有效数据请求）
                step.network = relevant_networks[0]["data"]
                
            final_steps.append(step)

        return final_steps
