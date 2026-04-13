import json

with open('server/app/routers/page_tree.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 build_tree_response，添加注释字段到响应
old_node_build = '''        node = {
            "id": page.id,
            "project_id": page.project_id,
            "parent_id": page.parent_id,
            "name": page.name,
            "path": page.path,
            "full_path": page.full_path,
            "is_leaf": page.is_leaf,
            "component_name": page.component_name,
            "components": components,  # 新增：组件列表
            "description": page.description or "",
            "children": [],
            "case_count": case_counts.get(page.id, 0),
        }'''

new_node_build = '''        node = {
            "id": page.id,
            "project_id": page.project_id,
            "parent_id": page.parent_id,
            "name": page.name,
            "path": page.path,
            "full_path": page.full_path,
            "is_leaf": page.is_leaf,
            "component_name": page.component_name,
            "components": components,  # 组件列表
            "page_comments": page.page_comments or "",  # 页面注释
            "component_comments": page.component_comments or "",  # 组件注释（JSON字符串）
            "description": page.description or "",
            "children": [],
            "case_count": case_counts.get(page.id, 0),
        }'''

content = content.replace(old_node_build, new_node_build)

with open('server/app/routers/page_tree.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_tree.py 已更新，API 响应中包含注释信息')
