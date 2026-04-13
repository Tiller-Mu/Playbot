import json

with open('server/app/services/page_component_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改输出要求，增加字数限制
old_requirement = '''**输出要求**：
- 必须使用**中文**
- 一句话描述，20-50字
- 包含主要功能和操作

## 输出格式（JSON）

```json
{{
  "page_name": "{page_name}",
  "description": "用户列表页面，展示用户信息并支持搜索、分页和编辑操作",
  "components": {component_names[:10]}  // 最多返回10个组件
}}
```

**注意**：
- 只返回JSON，不要其他内容
- description必须是一句话
- components返回组件名数组即可'''

new_requirement = '''**输出要求**：
- 必须使用**中文**
- 详细描述，**100-200字**
- 包含以下内容：
  1. 页面的主要功能
  2. 核心交互操作（增删改查、筛选、分页等）
  3. 关键组件的作用
  4. 数据展示方式（列表、表单、图表等）

## 输出格式（JSON）

```json
{{
  "page_name": "{page_name}",
  "description": "这是一个完整的用户管理页面，主要用于展示和维护系统用户信息。页面顶部提供搜索栏，支持按用户名、邮箱等条件进行筛选。主体部分采用数据表格展示用户列表，支持分页浏览、排序和批量操作。每行数据提供编辑和删除按钮，方便管理员快速维护用户信息。页面还集成了权限管理功能，可以设置不同用户的访问权限。",
  "components": {component_names[:10]}  // 最多返回10个组件
}}
```

**注意**：
- 只返回JSON，不要其他内容
- **description必须是100-200字的详细描述**
- components返回组件名数组即可'''

content = content.replace(old_requirement, new_requirement)

with open('server/app/services/page_component_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_component_analyzer.py 已更新，LLM现在会返回100-200字的详细描述')
