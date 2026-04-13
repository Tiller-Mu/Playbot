import json

with open('server/app/routers/page_tree.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改保存页面树的代码，添加注释字段保存
old_save = '''            # 保存 imported_components（静态分析的组件引用）
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

new_save = '''            # 保存静态分析的数据
            imported_components = node.get("imported_components", [])
            page_comments = node.get("page_comments", "")
            component_comments = node.get("component_comments", {})
            
            page = TestPage(
                project_id=project_id,
                parent_id=parent_id,
                name=node.get("name", ""),
                path=node.get("path", ""),
                full_path=node.get("full_path", ""),
                is_leaf=node.get("is_leaf", False),
                component_name=node.get("component"),
                imported_components=json.dumps(imported_components, ensure_ascii=False) if imported_components else None,
                page_comments=page_comments if page_comments else None,
                component_comments=json.dumps(component_comments, ensure_ascii=False) if component_comments else None,
            )'''

content = content.replace(old_save, new_save)

with open('server/app/routers/page_tree.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_tree.py 已更新，现在会保存注释信息到数据库')
