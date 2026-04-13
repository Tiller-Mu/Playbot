import json

with open('server/app/routers/page_tree.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 build_tree_response 函数中添加 components 字段解析
old_node = '''    # 创建所有节点
    for page in pages:
        node = {
            "id": page.id,
            "project_id": page.project_id,
            "parent_id": page.parent_id,
            "name": page.name,
            "path": page.path,
            "full_path": page.full_path,
            "is_leaf": page.is_leaf,
            "component_name": page.component_name,
            "description": page.description or "",
            "children": [],
            "case_count": case_counts.get(page.id, 0),
        }
        page_map[page.id] = node'''

new_node = '''    # 创建所有节点
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
                components = [page.component_name] if page.component_name else []
        
        node = {
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
        }
        page_map[page.id] = node'''

content = content.replace(old_node, new_node)

with open('server/app/routers/page_tree.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ build_tree_response 已优化，现在会解析并返回 components 字段')
