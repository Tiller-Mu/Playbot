import json

with open('server/app/routers/generate.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改保存逻辑，同时保存组件列表
old_save = '''        if result:
            # 更新页面信息
            page.description = result.get("description", "")
            await db.commit()
            
            await send_log("success", f"✓ 页面分析完成: {page.name} - {page.description[:50]}")'''

new_save = '''        if result:
            # 更新页面信息
            page.description = result.get("description", "")
            
            # 保存组件列表（去重）
            components = result.get("components", [])
            if components:
                # 去重并保持顺序
                seen = set()
                unique_components = []
                for comp in components:
                    if comp not in seen:
                        seen.add(comp)
                        unique_components.append(comp)
                
                page.component_name = json.dumps(unique_components, ensure_ascii=False)
                await send_log("info", f"📦 保存 {len(unique_components)} 个组件: {', '.join(unique_components[:5])}...")
            
            await db.commit()
            
            await send_log("success", f"✓ 页面分析完成: {page.name} - {page.description[:50]}")'''

content = content.replace(old_save, new_save)

with open('server/app/routers/generate.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ generate.py 已更新，现在会保存组件列表到数据库')
