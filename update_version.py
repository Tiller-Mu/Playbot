# 更新版本号到 0.1.8

# 更新后端版本
with open('server/pyproject.toml', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('version = "0.1.7"', 'version = "0.1.8"')
with open('server/pyproject.toml', 'w', encoding='utf-8') as f:
    f.write(content)
print('✅ 后端版本号更新为 0.1.8')

# 更新前端版本
with open('client/package.json', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('"version": "0.1.7"', '"version": "0.1.8"')
with open('client/package.json', 'w', encoding='utf-8') as f:
    f.write(content)
print('✅ 前端版本号更新为 0.1.8')

print('\n🎉 版本号更新完成！')
