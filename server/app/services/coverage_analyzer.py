"""覆盖率分析器 - 对比录制页面与静态路由，生成覆盖率报告"""
import re
import os
import logging
from typing import Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


class CoverageAnalyzer:
    """覆盖率分析器"""
    
    def analyze(self, session, repo_path: str) -> dict:
        """分析录制覆盖率"""
        try:
            # 步骤1：静态分析所有路由
            static_pages = self._extract_vue_routes(repo_path)
            
            logger.info(f"[覆盖率分析] 静态路由数量: {len(static_pages)}")
            logger.info(f"[覆盖率分析] 已录制页面数量: {len(session.discovered_pages)}")
            
            # 步骤2：对比分析
            recorded_patterns = set(session.discovered_pages.keys())
            static_patterns = set(static_pages.keys())
            
            missed_patterns = static_patterns - recorded_patterns
            
            # 步骤3：分类和优先级
            missed_pages = []
            for pattern in missed_patterns:
                page_info = static_pages[pattern]
                missed_pages.append({
                    'pattern': pattern,
                    'url': page_info.get('example_url', pattern),
                    'type': self._classify_page(pattern),
                    'priority': self._estimate_priority(pattern)
                })
            
            # 按优先级排序
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            missed_pages.sort(key=lambda x: priority_order.get(x['priority'], 3))
            
            # 步骤4：计算覆盖率
            total = len(static_patterns)
            covered = len(recorded_patterns)
            
            logger.info(f"[覆盖率分析] 总页面: {total}, 已录制: {covered}, 遗漏: {len(missed_pages)}")
            
            # 如果没有静态路由，使用录制的页面数据
            if total == 0 and covered > 0:
                logger.warning(f"[覆盖率分析] 未找到静态路由，但已录制 {covered} 个页面")
                return {
                    'coverage_rate': 1.0,  # 100%（因为没有基准）
                    'recorded_count': covered,
                    'missed_count': 0,
                    'missed_pages': [],
                    'suggestions': [
                        f'✅ 成功录制 {covered} 个页面',
                        '⚠️ 无法对比覆盖率（未找到路由配置文件），请检查项目结构',
                        f'录制的页面: {", ".join(list(recorded_patterns)[:5])}'
                    ]
                }
            
            return {
                'coverage_rate': covered / total if total > 0 else 0,
                'recorded_count': covered,
                'missed_count': len(missed_pages),
                'missed_pages': missed_pages,
                'suggestions': self._generate_suggestions(covered, total)
            }
        except Exception as e:
            logger.error(f"[覆盖率分析] 失败: {e}", exc_info=True)
            return {
                'coverage_rate': 0,
                'recorded_count': 0,
                'missed_count': 0,
                'missed_pages': [],
                'suggestions': [f'覆盖率分析失败: {str(e)}']
            }
    
    def _extract_vue_routes(self, repo_path: str) -> Dict[str, dict]:
        """从Vue Router提取所有路由"""
        routes = {}
        
        try:
            router_dir = Path(repo_path) / 'src' / 'router'
            if not router_dir.exists():
                logger.warning(f"[覆盖率分析] 未找到router目录: {router_dir}")
                return routes
            
            # 查找路由配置文件
            route_files = list(router_dir.glob('*.js')) + list(router_dir.glob('*.ts'))
            
            for route_file in route_files:
                logger.debug(f"[覆盖率分析] 解析路由文件: {route_file}")
                file_routes = self._parse_route_file(route_file)
                routes.update(file_routes)
            
            logger.info(f"[覆盖率分析] 从静态分析提取 {len(routes)} 个路由")
            
        except Exception as e:
            logger.error(f"[覆盖率分析] 提取Vue路由失败: {e}", exc_info=True)
        
        return routes
    
    def _parse_route_file(self, route_file: Path) -> Dict[str, dict]:
        """解析路由文件，提取路由定义"""
        routes = {}
        
        try:
            content = route_file.read_text(encoding='utf-8')
            
            # 简单正则匹配路由路径（支持多种格式）
            # 匹配: path: '/xxx' 或 path: '/xxx/:id'
            path_pattern = r"path:\s*['\"]([^'\"]+)['\"]"
            matches = re.finditer(path_pattern, content)
            
            for match in matches:
                path = match.group(1)
                
                # 跳过空路径和注释
                if not path or path.startswith('//'):
                    continue
                
                # 生成示例URL（将参数替换为示例值）
                example_url = path
                if ':id' in path:
                    example_url = path.replace(':id', '1')
                elif ':' in path:
                    # 其他参数替换为示例值
                    example_url = re.sub(r':\w+', 'example', path)
                
                routes[path] = {
                    'example_url': example_url,
                    'source_file': str(route_file)
                }
                
                logger.debug(f"[覆盖率分析] 提取路由: {path}")
        
        except Exception as e:
            logger.error(f"[覆盖率分析] 解析路由文件失败 {route_file}: {e}")
        
        return routes
    
    def _classify_page(self, pattern: str) -> str:
        """分类遗漏页面的类型"""
        if any(kw in pattern for kw in ['/login', '/register', '/auth']):
            return 'auth'
        elif any(kw in pattern for kw in ['/dashboard', '/home', '/index']):
            return 'dashboard'
        elif '/settings' in pattern:
            return 'settings'
        elif any(kw in pattern for kw in ['/edit', '/create', '/new', '/add']):
            return 'edit_form'
        elif any(kw in pattern for kw in ['/detail', '/view', '/info']):
            return 'detail'
        elif any(kw in pattern for kw in ['/list', '/table', '/grid']):
            return 'list'
        else:
            return 'other'
    
    def _estimate_priority(self, pattern: str) -> str:
        """评估页面重要性"""
        # 高优先级：认证、首页、核心功能
        if any(kw in pattern for kw in ['/login', '/dashboard', '/home', '/project', '/test']):
            return 'high'
        
        # 中优先级：设置、管理、编辑
        elif any(kw in pattern for kw in ['/settings', '/admin', '/edit', '/create']):
            return 'medium'
        
        # 低优先级：详情、帮助、关于
        else:
            return 'low'
    
    def _generate_suggestions(self, covered: int, total: int) -> List[str]:
        """生成建议"""
        suggestions = []
        
        if total == 0:
            suggestions.append('未检测到路由，请检查项目结构')
            return suggestions
        
        coverage_rate = covered / total
        
        if coverage_rate >= 0.9:
            suggestions.append('覆盖率优秀，可以开始生成测试用例')
        elif coverage_rate >= 0.7:
            suggestions.append('覆盖率良好，建议补充录制遗漏的高优先级页面')
        elif coverage_rate >= 0.5:
            suggestions.append('覆盖率中等，建议继续录制以提高测试质量')
        else:
            suggestions.append('覆盖率较低，建议完成主要页面的录制')
        
        return suggestions
