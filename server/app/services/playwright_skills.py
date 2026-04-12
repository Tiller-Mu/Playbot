"""MCP Skills - 基于Playwright CLI的页面分析工具集。"""
import subprocess
import logging
import json
import tempfile
from pathlib import Path
from typing import Optional
import base64

logger = logging.getLogger(__name__)


class PlaywrightCLISkills:
    """Playwright CLI技能集合 - 封装常用命令（Windows兼容）"""
    
    def __init__(self, project_id: str = ""):
        self.project_id = project_id
        self.temp_dir = Path(tempfile.gettempdir()) / f"playbot_{project_id}"
        self.temp_dir.mkdir(exist_ok=True)
    
    def take_screenshot(
        self,
        url: str,
        output_path: Optional[str] = None,
        full_page: bool = True,
        timeout: int = 30000,
        device: str = ""
    ) -> dict:
        """
        Skill 1: 页面快照采集
        
        参数:
            url: 页面URL
            output_path: 输出路径（可选）
            full_page: 是否完整页面
            timeout: 超时时间
            device: 设备模拟（如iPhone 12）
        
        返回:
            {
                "success": bool,
                "screenshot_base64": str,
                "screenshot_path": str,
                "dimensions": {"width": int, "height": int},
                "error": str (if failed)
            }
        """
        if not output_path:
            output_path = str(self.temp_dir / f"screenshot_{abs(hash(url))}.png")
        
        cmd = ["playwright", "screenshot", url, output_path]
        
        if full_page:
            cmd.append("--full-page")
        
        if device:
            cmd.extend(["--device", device])
        
        cmd.extend(["--timeout", str(timeout)])
        
        logger.info(f"[Skill:Screenshot] 执行命令: {' '.join(cmd)}")
        
        try:
            # 使用同步subprocess.run（Windows兼容）
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 60秒超时
            )
            
            if result.returncode == 0:
                # 读取截图并转换为Base64
                screenshot_bytes = Path(output_path).read_bytes()
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                
                # 获取图片尺寸（使用PIL）
                try:
                    from PIL import Image
                    from io import BytesIO
                    img = Image.open(BytesIO(screenshot_bytes))
                    dimensions = {"width": img.width, "height": img.height}
                except:
                    dimensions = {"width": 0, "height": 0}
                
                logger.info(f"[Skill:Screenshot] 截图成功: {output_path}")
                
                return {
                    "success": True,
                    "screenshot_base64": screenshot_base64,
                    "screenshot_path": output_path,
                    "dimensions": dimensions
                }
            else:
                error_msg = result.stderr or result.stdout or "未知错误"
                logger.error(f"[Skill:Screenshot] 失败: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except subprocess.TimeoutExpired:
            logger.error(f"[Skill:Screenshot] 超时")
            return {
                "success": False,
                "error": "命令执行超时"
            }
        except Exception as e:
            logger.error(f"[Skill:Screenshot] 异常: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def extract_dom_tree(
        self,
        url: str,
        max_depth: int = 5,
        timeout: int = 30000
    ) -> dict:
        """
        Skill 4: DOM树提取
        
        参数:
            url: 页面URL
            max_depth: 最大深度
            timeout: 超时时间
        
        返回:
            {
                "success": bool,
                "dom_tree": dict,
                "total_elements": int,
                "error": str (if failed)
            }
        """
        js_code = f"""
        (() => {{
            function buildTree(element, depth) {{
                if (depth > {max_depth}) return null;
                
                const node = {{
                    tag: element.tagName.toLowerCase(),
                    id: element.id || '',
                    classes: Array.from(element.classList),
                    text: element.innerText?.substring(0, 100) || '',
                    children: []
                }};
                
                for (const child of element.children) {{
                    const childNode = buildTree(child, depth + 1);
                    if (childNode) node.children.push(childNode);
                }}
                
                return node;
            }}
            
            const tree = buildTree(document.body, 0);
            const totalElements = document.querySelectorAll('*').length;
            
            return {{ tree, totalElements }};
        }})()
        """
        
        cmd = [
            "playwright",
            "eval",
            url,
            js_code,
            "--timeout", str(timeout)
        ]
        
        logger.info(f"[Skill:DOM] 提取DOM树...")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                dom_result = json.loads(result.stdout)
                
                return {
                    "success": True,
                    "dom_tree": dom_result.get("tree"),
                    "total_elements": dom_result.get("totalElements", 0)
                }
            else:
                error_msg = result.stderr or result.stdout or "未知错误"
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "命令执行超时"
            }
        except Exception as e:
            logger.error(f"[Skill:DOM] 异常: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def analyze_accessibility(
        self,
        url: str,
        timeout: int = 30000
    ) -> dict:
        """
        Skill 5: 无障碍分析
        
        参数:
            url: 页面URL
            timeout: 超时时间
        
        返回:
            {
                "success": bool,
                "issues": list,
                "total_issues": int,
                "accessibility_score": int,
                "error": str (if failed)
            }
        """
        js_code = """
        (() => {
            const issues = [];
            
            document.querySelectorAll('img:not([alt])').forEach(img => {
                issues.push({
                    type: 'missing_alt',
                    element: 'img',
                    src: img.src.substring(0, 100)
                });
            });
            
            document.querySelectorAll('input:not([aria-label]):not([id])').forEach(input => {
                issues.push({
                    type: 'missing_label',
                    element: input.type || 'input',
                    name: input.name || ''
                });
            });
            
            document.querySelectorAll('button:not([aria-label])').forEach(btn => {
                if (!btn.innerText.trim()) {
                    issues.push({
                        type: 'empty_button',
                        element: 'button'
                    });
                }
            });
            
            document.querySelectorAll('a:not([aria-label])').forEach(link => {
                if (!link.innerText.trim() && !link.querySelector('img')) {
                    issues.push({
                        type: 'empty_link',
                        element: 'a',
                        href: link.href
                    });
                }
            });
            
            return {
                issues,
                total_issues: issues.length,
                accessibility_score: Math.max(0, 100 - issues.length * 5)
            };
        })()
        """
        
        cmd = [
            "playwright",
            "eval",
            url,
            js_code,
            "--timeout", str(timeout)
        ]
        
        logger.info(f"[Skill:A11y] 无障碍分析...")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                a11y_result = json.loads(result.stdout)
                
                return {
                    "success": True,
                    "issues": a11y_result.get("issues", []),
                    "total_issues": a11y_result.get("total_issues", 0),
                    "accessibility_score": a11y_result.get("accessibility_score", 100)
                }
            else:
                error_msg = result.stderr or result.stdout or "未知错误"
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "命令执行超时"
            }
        except Exception as e:
            logger.error(f"[Skill:A11y] 异常: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
