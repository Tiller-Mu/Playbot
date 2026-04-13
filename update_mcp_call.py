import json

with open('server/app/services/page_component_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 analyze_single_page 函数，从 page_component 中提取注释并传给 _analyze_with_llm
old_call = '''            # 使用LLM分析页面
            await self._send_log("info", f"开始LLM分析页面: {page_name}")
            analysis_result = await self._analyze_with_llm(
                page_name=page_name,
                page_route=page_route,
                page_source=page_source,
                components_summary=components_summary,
                global_rules=global_rules
            )'''

new_call = '''            # 从 page_component 中提取注释信息
            page_comments = page_component.get("page_comments", "")
            component_comments_str = page_component.get("component_comments", "{}")
            
            # 解析组件注释（JSON字符串转字典）
            try:
                component_comments = json.loads(component_comments_str) if component_comments_str else {}
            except:
                component_comments = {}
            
            # 使用LLM分析页面
            await self._send_log("info", f"开始LLM分析页面: {page_name}")
            analysis_result = await self._analyze_with_llm(
                page_name=page_name,
                page_route=page_route,
                page_source=page_source,
                components_summary=components_summary,
                global_rules=global_rules,
                page_comments=page_comments,
                component_comments=component_comments
            )'''

content = content.replace(old_call, new_call)

with open('server/app/services/page_component_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_component_analyzer.py 已更新，调用LLM分析时会传入注释信息')
