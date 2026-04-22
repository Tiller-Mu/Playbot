"""页面树分析服务 - 从项目代码中提取多级页面树结构。"""
import os
from pathlib import Path
import asyncio
from typing import Any
from .comment_extractor import extract_vue_comments


async def extract_page_tree(repo_path: str) -> list[dict[str, Any]]:
    """
    从项目代码中提取多级页面树结构
    只识别真正的页面（路由入口），排除普通组件
    
    返回: [{"name": "user", "path": "user", "children": [...], "is_leaf": false}]
    """
    repo = Path(repo_path)
    if not repo.exists():
        return []
    
    # 收集所有页面文件路径
    page_files = await _find_page_files(repo)
    
    if not page_files:
        return []
    
    # 构建页面树
    tree = _build_page_tree(page_files, repo)
    
    return tree


async def _find_page_files(repo: Path) -> list[dict[str, str]]:
    """
    查找所有页面文件（路由入口）
    返回: [{"full_path": "/login", "file_path": "src/app/login/page.tsx", "component": "LoginPage"}]
    """
    pages = []
    
    def _scan():
        # 1. Next.js App Router: app/**/page.tsx
        for pattern in ["app/**/page.*", "src/app/**/page.*"]:
            for page_file in repo.glob(pattern):
                if page_file.is_file():
                    rel_path = str(page_file.relative_to(repo))
                    # 计算路由路径
                    route_path = _nextjs_app_route_to_path(page_file, repo)
                    component_name = _extract_component_name(page_file)
                    pages.append({
                        "full_path": route_path,
                        "file_path": rel_path,
                        "component": component_name,
                    })
        
        # 2. Next.js Pages Router: pages/**/*.tsx (排除 _app, _document)
        for pattern in ["pages/**/*.tsx", "pages/**/*.js", "src/pages/**/*.tsx", "src/pages/**/*.js"]:
            for page_file in repo.glob(pattern):
                if page_file.is_file():
                    filename = page_file.stem
                    # 排除特殊文件
                    if filename.startswith('_') and filename in ['_app', '_document', '_error']:
                        continue
                    
                    rel_path = str(page_file.relative_to(repo))
                    route_path = _nextjs_pages_route_to_path(page_file, repo)
                    component_name = _extract_component_name(page_file)
                    pages.append({
                        "full_path": route_path,
                        "file_path": rel_path,
                        "component": component_name,
                    })
        
        # 3. Vue Router: src/views/**/*.vue, src/pages/**/*.vue 等
        for pattern in ["src/views/**/*.vue", "views/**/*.vue", "src/pages/**/*.vue", "pages/**/*.vue"]:
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
        
        return pages
    
    return await asyncio.to_thread(_scan)


def _nextjs_app_route_to_path(page_file: Path, repo: Path) -> str:
    """
    Next.js App Router: 从文件路径转换为路由路径
    src/app/user/settings/page.tsx → /user/settings
    app/login/page.tsx → /login
    app/user/[id]/profile/page.tsx → /user/[id]/profile
    """
    # 找到 app 或 src/app 目录
    rel_path = page_file.relative_to(repo)
    parts = rel_path.parts
    
    # 找到 'app' 的位置
    app_index = -1
    for i, part in enumerate(parts):
        if part == 'app':
            app_index = i
            break
    
    if app_index == -1:
        return "/"
    
    # 获取 app 目录之后的的路径
    route_parts = parts[app_index + 1:-1]  # 排除 page.tsx
    route_path = "/" + "/".join(route_parts) if route_parts else "/"
    
    return route_path


def _nextjs_pages_route_to_path(page_file: Path, repo: Path) -> str:
    """
    Next.js Pages Router: 从文件路径转换为路由路径
    pages/user/settings.tsx → /user/settings
    pages/login.tsx → /login
    pages/index.tsx → /
    """
    rel_path = page_file.relative_to(repo)
    parts = rel_path.parts
    
    # 找到 'pages' 的位置
    pages_index = -1
    for i, part in enumerate(parts):
        if part == 'pages':
            pages_index = i
            break
    
    if pages_index == -1:
        return "/"
    
    # 获取 pages 目录之后的的路径
    route_parts = parts[pages_index + 1:]
    
    # 处理 index 文件
    if len(route_parts) == 1 and route_parts[0] in ['index.tsx', 'index.js', 'index.jsx']:
        return "/"
    
    # 移除扩展名
    if route_parts:
        last_part = route_parts[-1]
        route_parts[-1] = last_part.rsplit('.', 1)[0]
        if route_parts[-1] == 'index':
            route_parts = route_parts[:-1]
    
    route_path = "/" + "/".join(route_parts) if route_parts else "/"
    return route_path


def _vue_route_to_path(page_file: Path, repo: Path) -> str:
    """
    Vue Router: 从文件路径转换为路由路径
    src/views/user/settings.vue → /user/settings
    views/login.vue → /login
    """
    rel_path = page_file.relative_to(repo)
    parts = rel_path.parts
    
    # 找到 'views' 或 'pages' 的位置
    views_index = -1
    for i, part in enumerate(parts):
        if part in ('views', 'pages'):
            views_index = i
            break
    
    if views_index == -1:
        return "/"
    
    # 获取 views 目录之后的的路径
    route_parts = list(parts[views_index + 1:])  # 转换为列表以便修改
    
    # 移除扩展名
    if route_parts:
        last_part = route_parts[-1]
        route_parts[-1] = last_part.rsplit('.', 1)[0]
        if route_parts[-1] == 'index':
            route_parts = route_parts[:-1]
    
    route_path = "/" + "/".join(route_parts) if route_parts else "/"
    return route_path


def _extract_component_name(page_file: Path) -> str:
    """从页面文件中提取组件名称"""
    try:
        content = page_file.read_text(errors="ignore")
        import re
        
        # 尝试匹配: export default function ComponentName
        match = re.search(r'export\s+default\s+function\s+(\w+)', content)
        if match:
            return match.group(1)
        
        # 尝试匹配: export default ComponentName
        match = re.search(r'export\s+default\s+(\w+)', content)
        if match:
            return match.group(1)
        
        # 尝试匹配: const ComponentName = 
        match = re.search(r'const\s+(\w+)\s*=\s*(?:defineComponent|.*?=>)', content)
        if match:
            return match.group(1)
        
        # 使用文件名作为组件名
        return page_file.stem
    except Exception:
        return page_file.stem


def _build_page_tree(page_files: list[dict], repo: Path) -> list[dict[str, Any]]:
    """
    从页面文件列表构建多级树
    [
      {"full_path": "/user/settings", "file_path": "src/app/user/settings/page.tsx"},
      {"full_path": "/user/profile", "file_path": "src/app/user/profile/page.tsx"},
    ]
    →
    [
      {
        "name": "user",
        "path": "user",
        "full_path": "/user",
        "is_leaf": false,
        "children": [
          {
            "name": "settings",
            "path": "settings",
            "full_path": "/user/settings",
            "is_leaf": true,
            "component": "SettingsPage"
          },
          ...
        ]
      }
    ]
    """
    root: dict[str, Any] = {"name": "root", "path": "", "full_path": "/", "is_leaf": False, "children": []}
    
    for page_file in page_files:
        full_path = page_file["full_path"]
        # 拆分路径
        parts = [p for p in full_path.split("/") if p]
        
        current = root
        current_path = ""
        
        for i, part in enumerate(parts):
            current_path = "/" + "/".join(parts[:i+1])
            is_leaf = (i == len(parts) - 1)
            
            # 查找或创建节点
            existing_node = None
            # 确保children是列表
            if current.get("children") is None:
                current["children"] = []
            for child in current["children"]:
                if child["path"] == part:
                    existing_node = child
                    break
            
            if existing_node:
                current = existing_node
            else:
                new_node = {
                    "name": part,
                    "path": part,
                    "full_path": current_path,
                    "is_leaf": is_leaf,
                    "children": [] if not is_leaf else None,
                }
                
                if is_leaf:
                    new_node["component"] = page_file.get("component", part)
                    new_node["file_path"] = page_file.get("file_path", "")
                    new_node["children"] = None  # 叶子节点没有 children
                
                current["children"].append(new_node)
                current = new_node
    
    return root["children"]


def _extract_imported_components(page_file: Path, repo: Path) -> list[str]:
    """
    静态分析页面文件，提取引用的组件列表
    
    策略：
    1. 扫描 import 语句
    2. 过滤掉 node_modules、utils、api 等非组件引用
    3. 保留 components、views 等目录的引用
    4. 提取组件名称（从导入路径或默认导出）
    """
    import re
    try:
        content = page_file.read_text(encoding='utf-8', errors='ignore')
        components = set()
        
        # 匹配 import 语句的通用正则
        pattern = r"import\s+(.*?)\s+from\s+[\x27\x22]([^\x27\x22]+)[\x27\x22]"
        
        # 非组件目录（需要排除）
        exclude_dirs = {'utils', 'api', 'services', 'store', 'router', 'config', 'assets', 'styles', 'types'}
        # 组件目录（需要保留）
        component_dirs = {'components', 'views', 'pages', 'layouts'}
        
        for line in content.split('\n'):
            line = line.strip()
            if not line.startswith('import'):
                continue
            
            matches = re.finditer(pattern, line)
            for match in matches:
                imports_str = match.group(1).strip()
                import_path = match.group(2).strip()
                
                # 解析诸如 A, { B, C as D } 的语法
                names_to_add = []
                clean_str = imports_str.replace('{', '').replace('}', '')
                for name in clean_str.split(','):
                    name = name.strip().split(' as ')[-1].strip()
                    # 我们过滤出符合大写开头的常见组件命名约定
                    if name and name.isidentifier() and name[0].isupper():
                        names_to_add.append(name)
                
                if names_to_add:
                    # 我们只取第一个名字做路径猜测校验
                    if _is_component_import(import_path, names_to_add[0], exclude_dirs, component_dirs):
                        components.update(names_to_add)
        
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
