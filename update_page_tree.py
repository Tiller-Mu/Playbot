import json

with open('server/app/routers/page_tree.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 build_tree_response 函数，优先使用 imported_components
old_parse = '''    # 创建所有节点
    for page in pages:
        # 解析 component_name 字段（JSON字符串或逗号分隔的字符串）
        components = []
        if page.component_name:
            try:
                # 尝试解析JSON
                if isinstance(page.component_name, str):
                    if page.component_name.startswith('['):
                        components = json.loads(page.component_name)
                    else:
                        # 逗号分隔的字符串
                        components = [c.strip() for c in page.component_name.split(',') if c.strip()]
                elif isinstance(page.component_name, list):
                    components = page.component_name
            except:
                # 解析失败，当作单个组件名
                components = [page.component_name] if page.component_name else []'''

new_parse = '''    # 创建所有节点
    for page in pages:
        # 优先使用静态分析的 imported_components，其次使用 component_name
        components = []
        
        # 1. 优先使用 imported_components（从页面源码静态分析得到）
        if hasattr(page, 'imported_components') and page.imported_components:
            components = page.imported_components
        # 2. 其次使用 component_name（从 MCP 分析或数据库得到）
        elif page.component_name:
            try:
                # 尝试解析JSON
                if isinstance(page.component_name, str):
                    if page.component_name.startswith('['):
                        components = json.loads(page.component_name)
                    else:
                        # 逗号分隔的字符串
                        components = [c.strip() for c in page.component_name.split(',') if c.strip()]
                elif isinstance(page.component_name, list):
                    components = page.component_name
            except:
                # 解析失败，当作单个组件名
                components = [page.component_name] if page.component_name else []'''

content = content.replace(old_parse, new_parse)

with open('server/app/routers/page_tree.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_tree.py 已优化，优先使用静态分析的 imported_components')
