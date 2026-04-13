import json

# 1. 修改数据库模型，添加 imported_components 字段
with open('server/app/models/database.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_model = '''    component_name = Column(Text, comment="组件名称列表（JSON格式）")
    description = Column(Text, comment="页面功能描述（Markdown格式）")'''

new_model = '''    component_name = Column(Text, comment="组件名称列表（JSON格式）")
    imported_components = Column(Text, comment="静态分析的组件引用列表（JSON格式）")
    description = Column(Text, comment="页面功能描述（Markdown格式）")'''

content = content.replace(old_model, new_model)

with open('server/app/models/database.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ 数据库模型已更新，添加 imported_components 字段')

# 2. 修改 page_tree.py，保存 imported_components
with open('server/app/routers/page_tree.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_save = '''            page = TestPage(
                project_id=project_id,
                parent_id=parent_id,
                name=node.get("name", ""),
                path=node.get("path", ""),
                full_path=node.get("full_path", ""),
                is_leaf=node.get("is_leaf", False),
                component_name=node.get("component"),
            )'''

new_save = '''            # 保存 imported_components（静态分析的组件引用）
            imported_components = node.get("imported_components", [])
            
            page = TestPage(
                project_id=project_id,
                parent_id=parent_id,
                name=node.get("name", ""),
                path=node.get("path", ""),
                full_path=node.get("full_path", ""),
                is_leaf=node.get("is_leaf", False),
                component_name=node.get("component"),
                imported_components=json.dumps(imported_components, ensure_ascii=False) if imported_components else None,
            )'''

content = content.replace(old_save, new_save)

with open('server/app/routers/page_tree.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_tree.py 已更新，保存 imported_components 到数据库')
