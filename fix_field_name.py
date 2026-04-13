import json

with open('server/app/routers/generate.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改读取组件列表的逻辑，使用正确的字段名
old_read = '''            # 保存组件列表（去重）
            components = result.get("components", [])
            if components:'''

new_read = '''            # 保存组件列表（去重）
            # 注意：page_component_analyzer返回的字段名是detected_components
            components = result.get("detected_components", result.get("components", []))
            if components:'''

content = content.replace(old_read, new_read)

with open('server/app/routers/generate.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ generate.py 已修复，现在使用正确的字段名 detected_components')
