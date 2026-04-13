# 修复正则表达式
import re

with open('server/app/services/page_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 使用ASCII码替换引号
content = content.replace(
    """        import_patterns = [
            r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]",  # import Xxx from 'yyy'
            r"import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]",  # import { Xxx } from 'yyy'
        ]""",
    """        import_patterns = [
            r"import\s+(\w+)\s+from\s+[\x27\x22]([^\x27\x22]+)[\x27\x22]",  # import Xxx from 'yyy'
            r"import\s+\{([^}]+)\}\s+from\s+[\x27\x22]([^\x27\x22]+)[\x27\x22]",  # import { Xxx } from 'yyy'
        ]"""
)

with open('server/app/services/page_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ 正则表达式已修复（使用ASCII码）')
