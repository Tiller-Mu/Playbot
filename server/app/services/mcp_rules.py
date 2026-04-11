"""MCP 规则文件管理 - 加载和管理页面探索规则。"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MCPRulesLoader:
    """MCP 规则文件加载器"""
    
    def __init__(self, project_id: str):
        self.rules_dir = Path("workspace") / "rules" / project_id
        self.rules_dir.mkdir(parents=True, exist_ok=True)
    
    def load_global_rules(self) -> Optional[str]:
        """加载全局规则"""
        global_file = self.rules_dir / "_global.md"
        if global_file.exists():
            try:
                content = global_file.read_text(encoding="utf-8")
                logger.info(f"加载全局规则: {global_file}")
                return content
            except Exception as e:
                logger.error(f"读取全局规则失败: {e}")
        return None
    
    def load_page_rules(self, route: str) -> Optional[str]:
        """
        加载指定页面的规则
        
        路由转换规则:
        - /login → login.md
        - /user/settings → user-settings.md
        - / → index.md
        """
        # 将路由路径转换为文件名
        filename = route.strip("/").replace("/", "-") or "index"
        rule_file = self.rules_dir / f"{filename}.md"
        
        if rule_file.exists():
            try:
                content = rule_file.read_text(encoding="utf-8")
                logger.info(f"加载页面规则: {rule_file}")
                return content
            except Exception as e:
                logger.error(f"读取页面规则失败: {e}")
        
        return None
    
    def get_combined_rules(self, route: str) -> str:
        """
        合并全局规则和页面规则
        
        返回格式化的规则文本
        """
        rules = []
        
        # 先加载全局规则
        global_rules = self.load_global_rules()
        if global_rules:
            rules.append("## 全局规则\n\n" + global_rules)
        
        # 再加载页面规则
        page_rules = self.load_page_rules(route)
        if page_rules:
            rules.append("## 页面特定规则\n\n" + page_rules)
        
        if rules:
            return "\n\n".join(rules)
        
        return ""
    
    def save_rule(self, route: str, content: str) -> bool:
        """
        保存规则文件
        
        参数:
            route: 路由路径（如 /login）
            content: Markdown 内容
        
        返回:
            是否保存成功
        """
        try:
            if route == "_global":
                filename = "_global.md"
            else:
                filename = route.strip("/").replace("/", "-") or "index"
                filename = f"{filename}.md"
            
            rule_file = self.rules_dir / filename
            rule_file.write_text(content, encoding="utf-8")
            logger.info(f"保存规则文件: {rule_file}")
            return True
        except Exception as e:
            logger.error(f"保存规则文件失败: {e}")
            return False
    
    def delete_rule(self, route: str) -> bool:
        """删除规则文件"""
        try:
            if route == "_global":
                filename = "_global.md"
            else:
                filename = route.strip("/").replace("/", "-") or "index"
                filename = f"{filename}.md"
            
            rule_file = self.rules_dir / filename
            if rule_file.exists():
                rule_file.unlink()
                logger.info(f"删除规则文件: {rule_file}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除规则文件失败: {e}")
            return False
    
    def list_rules(self) -> list[dict]:
        """列出所有规则文件"""
        rules = []
        
        if not self.rules_dir.exists():
            return rules
        
        for rule_file in self.rules_dir.glob("*.md"):
            filename = rule_file.name
            
            # 转换为路由
            if filename == "_global.md":
                route = "_global"
                rule_type = "global"
            else:
                # login.md → /login, user-settings.md → /user/settings
                route_path = filename[:-3].replace("-", "/")
                route = "/" + route_path if route_path != "index" else "/"
                rule_type = "page"
            
            rules.append({
                "route": route,
                "type": rule_type,
                "filename": filename,
                "size": rule_file.stat().st_size
            })
        
        return rules
