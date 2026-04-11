"""页面树分析服务 - 从项目代码中提取多级页面树结构。"""
import os
from pathlib import Path
import asyncio
from typing import Any


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
        
        # 3. Vue Router: src/views/**/*.vue
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
    
    # 找到 'views' 的位置
    views_index = -1
    for i, part in enumerate(parts):
        if part == 'views':
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
