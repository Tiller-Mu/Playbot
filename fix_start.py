with open('start.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复npm命令
content = content.replace(
    '["npm", "run", "dev"]',
    '["cmd", "/c", "npm", "run", "dev"]'
)

with open('start.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ start.py 修复完成')
