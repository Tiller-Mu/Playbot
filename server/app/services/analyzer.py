"""代码分析引擎 - 分析 Web 项目源码，提取路由、页面、组件等信息。"""
import os
from pathlib import Path
import asyncio


async def analyze_project(repo_path: str) -> str:
    """Analyze a web project and return a structured summary for LLM consumption."""
    repo = Path(repo_path)
    if not repo.exists():
        return "项目路径不存在"

    results = []

    # Detect project type
    framework = await _detect_framework(repo)
    results.append(f"## 项目框架: {framework}")

    # Scan for routes
    routes = await _find_routes(repo, framework)
    if routes:
        results.append(f"\n## 路由/页面 ({len(routes)} 个)")
        for r in routes:
            results.append(f"- {r}")

    # Scan for key components/pages
    pages = await _find_pages(repo, framework)
    if pages:
        results.append(f"\n## 页面文件 ({len(pages)} 个)")
        for p in pages:
            results.append(f"- {p['path']}")
            if p.get('summary'):
                results.append(f"  内容摘要: {p['summary']}")

    # Scan for API endpoints
    apis = await _find_api_endpoints(repo, framework)
    if apis:
        results.append(f"\n## API 接口 ({len(apis)} 个)")
        for a in apis:
            results.append(f"- {a}")

    # Scan for forms and interactive elements
    forms = await _find_forms(repo)
    if forms:
        results.append(f"\n## 表单/交互元素 ({len(forms)} 个)")
        for f in forms:
            results.append(f"- {f}")

    if not any([routes, pages, apis, forms]):
        # Fallback: list all source files
        src_files = _list_source_files(repo)
        results.append(f"\n## 源文件列表 ({len(src_files)} 个)")
        for f in src_files[:50]:
            results.append(f"- {f}")

    return "\n".join(results)


async def _detect_framework(repo: Path) -> str:
    """Detect the frontend framework used."""
    pkg_json = repo / "package.json"
    if pkg_json.exists():
        content = pkg_json.read_text(errors="ignore")
        if "next" in content:
            return "Next.js (React)"
        if "nuxt" in content:
            return "Nuxt (Vue)"
        if "react" in content:
            return "React"
        if "vue" in content:
            return "Vue"
        if "angular" in content:
            return "Angular"
        if "svelte" in content:
            return "Svelte"
        return "Node.js (其他)"

    if (repo / "requirements.txt").exists() or (repo / "pyproject.toml").exists():
        return "Python Web"

    return "未知框架"


async def _find_routes(repo: Path, framework: str) -> list[str]:
    """Extract route definitions from the project."""
    routes = []

    def _scan():
        # Next.js App Router: app/**/page.tsx
        app_dir = repo / "app"
        src_app_dir = repo / "src" / "app"
        for base in [app_dir, src_app_dir]:
            if base.exists():
                for page_file in base.rglob("page.*"):
                    route = "/" + str(page_file.parent.relative_to(base)).replace("\\", "/")
                    route = route.replace("/page", "").rstrip("/") or "/"
                    routes.append(f"[Next.js] {route} → {page_file.relative_to(repo)}")

        # Next.js Pages Router: pages/**/*.tsx
        pages_dir = repo / "pages"
        src_pages_dir = repo / "src" / "pages"
        for base in [pages_dir, src_pages_dir]:
            if base.exists():
                for f in base.rglob("*"):
                    if f.is_file() and f.suffix in (".tsx", ".ts", ".jsx", ".js"):
                        if f.name.startswith("_"):
                            continue
                        route = "/" + str(f.relative_to(base)).replace("\\", "/")
                        route = route.rsplit(".", 1)[0]
                        if route.endswith("/index"):
                            route = route[:-6] or "/"
                        routes.append(f"[Pages] {route} → {f.relative_to(repo)}")

        # React Router: look for <Route path=
        for f in _iter_source_files(repo):
            try:
                content = f.read_text(errors="ignore")
                import re
                for match in re.finditer(r'<Route\s+[^>]*path=["\']([^"\']+)["\']', content):
                    routes.append(f"[React Router] {match.group(1)} → {f.relative_to(repo)}")
                # Vue Router
                for match in re.finditer(r'path:\s*["\']([^"\']+)["\']', content):
                    path = match.group(1)
                    if path.startswith("/"):
                        routes.append(f"[Vue Router] {path} → {f.relative_to(repo)}")
            except Exception:
                continue

        return routes

    return await asyncio.to_thread(_scan)


async def _find_pages(repo: Path, framework: str) -> list[dict]:
    """Find page/view files and extract a summary."""
    pages = []

    def _scan():
        patterns = [
            "src/pages/**/*", "src/views/**/*", "pages/**/*", "views/**/*",
            "app/**/page.*", "src/app/**/page.*",
        ]
        seen = set()
        for pattern in patterns:
            for f in repo.glob(pattern):
                if f.is_file() and f.suffix in (".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte"):
                    rel = str(f.relative_to(repo))
                    if rel in seen:
                        continue
                    seen.add(rel)
                    # Read first 50 lines for a quick summary
                    try:
                        lines = f.read_text(errors="ignore").split("\n")[:50]
                        summary = _extract_page_summary(lines)
                    except Exception:
                        summary = ""
                    pages.append({"path": rel, "summary": summary})
        return pages

    return await asyncio.to_thread(_scan)


async def _find_api_endpoints(repo: Path, framework: str) -> list[str]:
    """Find API endpoint definitions."""
    endpoints = []

    def _scan():
        import re
        # Next.js API routes
        for base in [repo / "app" / "api", repo / "src" / "app" / "api",
                      repo / "pages" / "api", repo / "src" / "pages" / "api"]:
            if base.exists():
                for f in base.rglob("*"):
                    if f.is_file() and f.suffix in (".ts", ".js"):
                        rel = str(f.relative_to(base))
                        route = "/api/" + rel.rsplit(".", 1)[0].replace("route", "").rstrip("/")
                        endpoints.append(f"[API] {route}")

        # Express / Fastify / Koa routes
        for f in _iter_source_files(repo):
            try:
                content = f.read_text(errors="ignore")
                for match in re.finditer(
                    r'\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
                    content, re.IGNORECASE
                ):
                    method = match.group(1).upper()
                    path = match.group(2)
                    endpoints.append(f"[{method}] {path} → {f.relative_to(repo)}")
            except Exception:
                continue
        return endpoints

    return await asyncio.to_thread(_scan)


async def _find_forms(repo: Path) -> list[str]:
    """Find form elements and interactive components."""
    forms = []

    def _scan():
        import re
        for f in _iter_source_files(repo):
            try:
                content = f.read_text(errors="ignore")
                rel = str(f.relative_to(repo))
                # HTML forms
                if "<form" in content.lower():
                    inputs = re.findall(r'<input[^>]*(?:name|placeholder)=["\']([^"\']*)["\']', content)
                    forms.append(f"表单 → {rel} (字段: {', '.join(inputs[:5])})")
                # Login/Register patterns
                if any(kw in content.lower() for kw in ["login", "signin", "register", "signup", "登录", "注册"]):
                    forms.append(f"登录/注册相关 → {rel}")
            except Exception:
                continue
        return forms

    return await asyncio.to_thread(_scan)


def _extract_page_summary(lines: list[str]) -> str:
    """Extract a brief summary from page source lines."""
    import re
    # Look for component name, title, heading text
    for line in lines:
        # export default function PageName
        m = re.search(r'(?:export\s+default\s+)?(?:function|class|const)\s+(\w+)', line)
        if m and m.group(1) not in ("default", "export"):
            return f"组件: {m.group(1)}"
        # <title> or document.title
        m = re.search(r'<title>([^<]+)</title>', line)
        if m:
            return f"标题: {m.group(1)}"
    return ""


def _iter_source_files(repo: Path):
    """Iterate over source files, skipping node_modules etc."""
    skip_dirs = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", ".nuxt"}
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f.endswith((".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte", ".py")):
                yield Path(root) / f


def _list_source_files(repo: Path) -> list[str]:
    """List all source files (fallback)."""
    return [str(f.relative_to(repo)) for f in _iter_source_files(repo)]
