import re

with open('server/app/services/page_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 在文件开头添加导入
old_imports = '"""页面树分析服务 - 从项目代码中提取多级页面树结构。"""\nimport os\nfrom pathlib import Path\nimport asyncio\nfrom typing import Any'

new_imports = '"""页面树分析服务 - 从项目代码中提取多级页面树结构。"""\nimport os\nfrom pathlib import Path\nimport asyncio\nfrom typing import Any\nfrom .comment_extractor import extract_vue_comments'

content = content.replace(old_imports, new_imports)

# 2. 修改 Vue Router 页面扫描部分，添加注释提取
old_vue_scan = '''        # 3. Vue Router: src/views/**/*.vue
        for pattern in ["src/views/**/*.vue", "views/**/*.vue"]:
            for page_file in repo.glob(pattern):
                if page_file.is_file():
                    rel_path = str(page_file.relative_to(repo))
                    route_path = _vue_route_to_path(page_file, repo)
                    component_name = _extract_component_name(page_file)
                    # 静态分析页面引用的组件
                    imported_components = _extract_imported_components(page_file, repo)
                    pages.append({
                        "full_path": route_path,
                        "file_path": rel_path,
                        "component": component_name,
                        "imported_components": imported_components,  # 新增：引用的组件列表
                    })
        
        return pages'''

new_vue_scan = '''        # 3. Vue Router: src/views/**/*.vue
        for pattern in ["src/views/**/*.vue", "views/**/*.vue"]:
            for page_file in repo.glob(pattern):
                if page_file.is_file():
                    rel_path = str(page_file.relative_to(repo))
                    route_path = _vue_route_to_path(page_file, repo)
                    component_name = _extract_component_name(page_file)
                    # 静态分析页面引用的组件
                    imported_components = _extract_imported_components(page_file, repo)
                    # 提取页面注释和组件注释
                    try:
                        file_content = page_file.read_text(encoding='utf-8', errors='ignore')
                        comments_info = extract_vue_comments(file_content)
                    except:
                        comments_info = {"page_comments": "", "component_comments": {}}
                    
                    pages.append({
                        "full_path": route_path,
                        "file_path": rel_path,
                        "component": component_name,
                        "imported_components": imported_components,
                        "page_comments": comments_info["page_comments"],
                        "component_comments": comments_info["component_comments"],
                    })
        
        return pages'''

content = content.replace(old_vue_scan, new_vue_scan)

with open('server/app/services/page_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_analyzer.py 已更新，现在会提取页面注释和组件注释')
