with open('server/app/services/page_analyzer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到并修复第320-321行
for i in range(len(lines)):
    if i == 319:  # 第320行（索引319）
        lines[i] = '            r"import\\s+(\\w+)\\s+from\\s+[\'\\"]([^\'\\"]+)[\'\\"]",  # import Xxx from \'yyy\'\n'
    elif i == 320:  # 第321行（索引320）
        lines[i] = '            r"import\\s+\\{([^}]+)\\}\\s+from\\s+[\'\\"]([^\'\\"]+)[\'\\"]",  # import { Xxx } from \'yyy\'\n'

with open('server/app/services/page_analyzer.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('✅ 正则表达式已修复')
