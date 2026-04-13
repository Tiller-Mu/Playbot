with open('server/app/services/page_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复正则表达式的引号转义问题
old_patterns = '''        import_patterns = [
            r"import\s+(\w+)\s+from\s+['"]([^'"]+)['"]",  # import Xxx from 'yyy'
            r"import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"]",  # import { Xxx } from 'yyy'
        ]'''

new_patterns = '''        import_patterns = [
            r"import\s+(\w+)\s+from\s+['\\\"]([^'\\\"]+)['\\\"]",  # import Xxx from 'yyy'
            r"import\s+\{([^}]+)\}\s+from\s+['\\\"]([^'\\\"]+)['\\\"]",  # import { Xxx } from 'yyy'
        ]'''

content = content.replace(old_patterns, new_patterns)

with open('server/app/services/page_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ 正则表达式引号转义已修复')
