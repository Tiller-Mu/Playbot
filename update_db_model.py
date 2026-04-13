import re

with open('server/app/models/database.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 检查是否已经添加了 imported_components 字段
if 'imported_components' not in content:
    # 添加 imported_components 字段
    old_model = '''    component_name = Column(Text, comment="组件名称列表（JSON格式）")
    description = Column(Text, comment="页面功能描述（Markdown格式）")'''
    
    new_model = '''    component_name = Column(Text, comment="组件名称列表（JSON格式）")
    imported_components = Column(Text, comment="静态分析的组件引用列表（JSON格式）")
    page_comments = Column(Text, comment="页面级注释（文件顶部注释等）")
    component_comments = Column(Text, comment="组件级注释（JSON格式：{组件名: 注释内容}）")
    description = Column(Text, comment="页面功能描述（Markdown格式）")'''
    
    content = content.replace(old_model, new_model)
    
    with open('server/app/models/database.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('✅ 数据库模型已更新，添加 page_comments 和 component_comments 字段')
else:
    # imported_components 已存在，只需添加注释字段
    if 'page_comments' not in content:
        old_model = '''    imported_components = Column(Text, comment="静态分析的组件引用列表（JSON格式）")
    description = Column(Text, comment="页面功能描述（Markdown格式）")'''
        
        new_model = '''    imported_components = Column(Text, comment="静态分析的组件引用列表（JSON格式）")
    page_comments = Column(Text, comment="页面级注释（文件顶部注释等）")
    component_comments = Column(Text, comment="组件级注释（JSON格式：{组件名: 注释内容}）")
    description = Column(Text, comment="页面功能描述（Markdown格式）")'''
        
        content = content.replace(old_model, new_model)
        
        with open('server/app/models/database.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print('✅ 数据库模型已更新，添加 page_comments 和 component_comments 字段')
    else:
        print('⚠️ 字段已存在，跳过')
