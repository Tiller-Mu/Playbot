import re

with open('server/app/services/page_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 修改 _find_page_files 函数，增加组件分析
old_find = '''        # 3. Vue Router: src/views/**/*.vue
        for pattern in ["src/views/**/*.vue", "views/**/*.vue"]:
            for page_file in repo.glob(pattern):
                if page_file.is_file():
                    rel_path = str(page_file.relative_to(repo))
                    route_path = _vue_route_to_path(page_file, repo)
                    component_name = _extract_component_name(page_file)
                    pages.append({
                        "full_path": route_path,
                        "file_path": rel_path,
                        "component": component_name,
                    })
        
        return pages'''

new_find = '''        # 3. Vue Router: src/views/**/*.vue
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

content = content.replace(old_find, new_find)

# 2. 在文件末尾添加新函数 _extract_imported_components
new_function = '''

def _extract_imported_components(page_file: Path, repo: Path) -> list[str]:
    """
    静态分析页面文件，提取引用的组件列表
    
    策略：
    1. 扫描 import 语句
    2. 过滤掉 node_modules、utils、api 等非组件引用
    3. 保留 components、views 等目录的引用
    4. 提取组件名称（从导入路径或默认导出）
    """
    try:
        content = page_file.read_text(encoding='utf-8', errors='ignore')
        components = set()
        
        # 匹配 import 语句
        # import Xxx from 'yyy'
        # import { Xxx } from 'yyy'
        # import Xxx, { Yyy } from 'yyy'
        import_patterns = [
            r"import\\s+(\\w+)\\s+from\\s+['\"]([^'\"]+)['\"]",  # import Xxx from 'yyy'
            r"import\\s+\\{([^}]+)\\}\\s+from\\s+['\"]([^'\"]+)['\"]",  # import { Xxx } from 'yyy'
        ]
        
        # 非组件目录（需要排除）
        exclude_dirs = {'utils', 'api', 'services', 'store', 'router', 'config', 'assets', 'styles', 'types'}
        # 组件目录（需要保留）
        component_dirs = {'components', 'views', 'pages', 'layouts'}
        
        for line in content.split('\\n'):
            line = line.strip()
            if not line.startswith('import'):
                continue
            
            # 尝试匹配 import 语句
            for pattern in import_patterns:
                matches = re.finditer(pattern, line)
                for match in matches:
                    if pattern.startswith(r"import\\s+(\\w+)"):
                        # import Xxx from 'yyy'
                        component_name = match.group(1)
                        import_path = match.group(2)
                    else:
                        # import { Xxx, Yyy } from 'yyy'
                        names = match.group(1).split(',')
                        import_path = match.group(2)
                        # 添加所有命名的导入
                        for name in names:
                            name = name.strip().split(' as ')[-1].strip()
                            if name and name.isidentifier():
                                components.add(name)
                        continue
                    
                    # 判断是否是组件引用
                    if _is_component_import(import_path, component_name, exclude_dirs, component_dirs):
                        components.add(component_name)
        
        return sorted(list(components))
        
    except Exception as e:
        # 分析失败返回空列表
        return []


def _is_component_import(import_path: str, component_name: str, exclude_dirs: set, component_dirs: set) -> bool:
    """判断导入是否是组件引用"""
    # 排除 node_modules
    if import_path.startswith('.') or import_path.startswith('/'):
        # 相对路径导入
        path_parts = import_path.replace('./', '').replace('../', '').split('/')
        
        # 检查路径中是否包含排除目录
        for part in path_parts:
            if part in exclude_dirs:
                return False
        
        # 检查路径中是否包含组件目录
        for part in path_parts:
            if part in component_dirs:
                return True
        
        # 如果路径以大写开头（组件名约定），也认为是组件
        if component_name and component_name[0].isupper():
            return True
        
        return False
    
    # 绝对路径导入（可能是第三方库）
    # 但如果是 @/components/Xxx 这种别名导入
    if '@/' in import_path:
        path_parts = import_path.split('@/')[1].split('/')
        for part in path_parts:
            if part in component_dirs:
                return True
    
    return False
'''

# 在文件末尾添加新函数
if not content.endswith('\n\n'):
    content = content.rstrip() + '\n'

content = content + new_function

with open('server/app/services/page_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ page_analyzer.py 已增强，现在会静态分析页面引用的组件')
