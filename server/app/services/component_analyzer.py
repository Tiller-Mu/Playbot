"""组件分析引擎 - 分析项目源码，提取组件列表和关系。"""
import os
import re
import logging
from pathlib import Path
import asyncio
from typing import Any

logger = logging.getLogger(__name__)


async def analyze_components(repo_path: str) -> dict[str, Any]:
    """
    分析 Web 项目源码，提取所有组件文件清单
    
    优化说明：
    - 静态扫描只输出组件文件清单（防止MCP遗漏）
    - 不再进行复杂的组件使用关系判断
    - 由MCP按需分析每个页面的组件引用关系
    
    返回: {
        "framework": "Vue",
        "components": [
            {"name": "UserForm", "file_path": "src/components/UserForm.vue", "type": "component"},
            {"name": "LoginPage", "file_path": "src/views/LoginPage.vue", "type": "page", "route": "/login"}
        ],
        "page_components": [...],
        "common_components": [...],
        "entry_points": ["/login", "/dashboard"]
    }
    """
    repo = Path(repo_path)
    if not repo.exists():
        return {
            "framework": "未知",
            "components": [],
            "page_components": [],
            "common_components": [],
            "entry_points": [],
            "error": "项目路径不存在"
        }
    
    # 检测框架
    framework = await _detect_framework(repo)
    
    # 扫描所有组件
    components = await _scan_components(repo, framework)
    
    # 区分页面组件和普通组件
    page_components = [c for c in components if c["type"] == "page"]
    common_components = [c for c in components if c["type"] == "component"]
    
    # 提取入口点（页面组件的路由）
    entry_points = [c["route"] for c in page_components if c.get("route")]
    
    return {
        "framework": framework,
        "components": components,
        "page_components": page_components,
        "common_components": common_components,
        "entry_points": entry_points
    }


async def _detect_framework(repo: Path) -> str:
    """检测项目使用的框架"""
    pkg_json = repo / "package.json"
    if pkg_json.exists():
        content = pkg_json.read_text(errors="ignore")
        if "next" in content:
            return "Next.js"
        if "nuxt" in content:
            return "Nuxt"
        if "react" in content:
            return "React"
        if "vue" in content:
            return "Vue"
        if "angular" in content:
            return "Angular"
        if "svelte" in content:
            return "Svelte"
    return "未知"


async def _scan_components(repo: Path, framework: str) -> list[dict]:
    """扫描所有组件文件"""
    components = []
    
    def _scan():
        # 1. 扫描页面组件（路由入口）
        page_files = _find_page_files(repo, framework)
        for page_file in page_files:
            component = _extract_component_info(page_file, repo, "page", framework)
            if component:
                components.append(component)
        
        # 2. 扫描普通组件
        common_files = _find_common_components(repo, framework)
        for comp_file in common_files:
            component = _extract_component_info(comp_file, repo, "component", framework)
            if component:
                components.append(component)
        
        return components
    
    return await asyncio.to_thread(_scan)


def _find_page_files(repo: Path, framework: str) -> list[Path]:
    """查找页面组件文件"""
    page_files = []
    
    # Next.js App Router: app/**/page.*
    for pattern in ["app/**/page.*", "src/app/**/page.*"]:
        page_files.extend(repo.glob(pattern))
    
    # Next.js Pages Router: pages/**/*.tsx
    for pattern in ["pages/**/*.tsx", "pages/**/*.js", "src/pages/**/*.tsx", "src/pages/**/*.js"]:
        for f in repo.glob(pattern):
            if f.is_file() and not f.name.startswith('_'):
                page_files.append(f)
    
    # Vue Router: src/views/**/*.vue
    for pattern in ["src/views/**/*.vue", "views/**/*.vue"]:
        page_files.extend(repo.glob(pattern))
    
    # React: src/pages/**/*.tsx
    for pattern in ["src/pages/**/*.tsx", "src/pages/**/*.jsx"]:
        page_files.extend(repo.glob(pattern))
    
    return [f for f in page_files if f.is_file()]


def _find_common_components(repo: Path, framework: str) -> list[Path]:
    """查找普通组件文件"""
    comp_files = []
    
    # 通用组件目录
    for pattern in ["src/components/**/*", "components/**/*"]:
        for f in repo.glob(pattern):
            if f.is_file() and f.suffix in ['.vue', '.tsx', '.jsx', '.ts', '.js']:
                comp_files.append(f)
    
    return comp_files


def _extract_component_info(
    file_path: Path, 
    repo: Path, 
    comp_type: str,
    framework: str
) -> dict | None:
    """
    提取组件基本信息（简化版）
    
    只输出：组件名称、文件路径、类型、路由（仅page）
    不再提取imports，由MCP按需分析
    """
    try:
        rel_path = str(file_path.relative_to(repo))
        
        # 读取文件内容仅用于提取组件名称
        content = file_path.read_text(errors="ignore")
        component_name = _extract_component_name(content, file_path)
        
        # 提取路由（仅页面组件）
        route = None
        if comp_type == "page":
            route = _extract_route(file_path, repo, framework)
        
        return {
            "type": comp_type,
            "name": component_name,
            "file_path": rel_path,
            "route": route,
        }
    except Exception as e:
        logger.warning(f"提取组件信息失败 {file_path}: {e}")
        return None


def _extract_component_name(content: str, file_path: Path) -> str:
    """从组件文件中提取组件名称"""
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
    
    # Vue: <script setup> 中的 name
    match = re.search(r'defineOptions\(\{.*?name:\s*["\'](\w+)["\']', content, re.DOTALL)
    if match:
        return match.group(1)
    
    # 使用文件名
    return file_path.stem


def _extract_route(file_path: Path, repo: Path, framework: str) -> str | None:
    """从页面文件路径提取路由"""
    rel_path = file_path.relative_to(repo)
    parts = rel_path.parts
    
    if framework in ["Next.js", "React"]:
        # Next.js App Router: app/user/settings/page.tsx → /user/settings
        if 'app' in parts:
            app_idx = parts.index('app')
            route_parts = parts[app_idx + 1:-1]  # 排除 page.tsx
            return "/" + "/".join(route_parts) if route_parts else "/"
        
        # Next.js Pages Router: pages/user/settings.tsx → /user/settings
        if 'pages' in parts:
            pages_idx = parts.index('pages')
            route_parts = list(parts[pages_idx + 1:])
            # 移除扩展名
            if route_parts:
                route_parts[-1] = route_parts[-1].rsplit('.', 1)[0]
                if route_parts[-1] == 'index':
                    route_parts = route_parts[:-1]
            return "/" + "/".join(route_parts) if route_parts else "/"
    
    elif framework in ["Vue", "Nuxt"]:
        # Vue Router: views/user/settings.vue → /user/settings
        if 'views' in parts:
            views_idx = parts.index('views')
            route_parts = list(parts[views_idx + 1:])
            if route_parts:
                route_parts[-1] = route_parts[-1].rsplit('.', 1)[0]
                if route_parts[-1] == 'index':
                    route_parts = route_parts[:-1]
            return "/" + "/".join(route_parts) if route_parts else "/"
    
    return None


def _extract_imports(content: str, framework: str) -> list[str]:
    """提取组件的 import 语句"""
    imports = []
    
    # ES6 import: import Component from './Component'
    matches = re.findall(r'import\s+(\w+)\s+from\s+["\']([^"\']+)["\']', content)
    for name, path in matches:
        # 只保留组件名（排除库导入）
        if not path.startswith(('@', '/', '.')) or not any(
            lib in path for lib in ['vue', 'react', 'axios', 'lodash']
        ):
            imports.append(name)
    
    return imports
