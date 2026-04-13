import json

with open('server/app/routers/generate.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 analyze_single_page 路由，将注释信息传给 analyzer
old_page_component = '''        result = await analyzer.analyze_page(
            page_component={
                'name': page.name,
                'file_path': file_path_str,
                'type': 'page',
                'route': page.full_path
            },
            components_list=components_list
        )'''

new_page_component = '''        result = await analyzer.analyze_page(
            page_component={
                'name': page.name,
                'file_path': file_path_str,
                'type': 'page',
                'route': page.full_path,
                'page_comments': page.page_comments or "",
                'component_comments': page.component_comments or "{}"
            },
            components_list=components_list
        )'''

content = content.replace(old_page_component, new_page_component)

with open('server/app/routers/generate.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ generate.py 已更新，单页分析时会传入注释信息')
