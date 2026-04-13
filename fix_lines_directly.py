# 直接修改文件行
with open('server/app/services/page_analyzer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 第320行和321行（索引319和320）
# 使用原始字符串，引号用\x27（单引号）和\x22（双引号）表示
lines[319] = '            r"import\\s+(\\w+)\\s+from\\s+[\\x27\\x22]([^\\x27\\x22]+)[\\x27\\x22]",  # import Xxx from quote\n'
lines[320] = '            r"import\\s+\\{([^}]+)\\}\\s+from\\s+[\\x27\\x22]([^\\x27\\x22]+)[\\x27\\x22]",  # import { Xxx } from quote\n'

with open('server/app/services/page_analyzer.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('✅ 已直接修改第320-321行')

# 验证
with open('server/app/services/page_analyzer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    print(f"第320行: {lines[319].rstrip()}")
    print(f"第321行: {lines[320].rstrip()}")
