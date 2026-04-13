with open('client/src/views/ProjectDetail.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 buildAssociations 函数，优先使用 API 返回的 components 字段
old_code = '''  const allPages = collectAllPages(pageTree.value)
  
  // 如果pageComponents已经有数据（从WebSocket收到的），直接使用
  // 否则从页面树数据中获取
  allPages.forEach(page => {
    // pageComponents中如果有数据就使用，没有就设为空数组
    if (!pageComponents.value[page.id]) {
      const components = (page as any).components || []
      pageComponents.value[page.id] = components
    }
  })'''

new_code = '''  const allPages = collectAllPages(pageTree.value)
  
  // 优先使用页面树API返回的components字段
  allPages.forEach(page => {
    // 优先使用 page.components（API返回），其次使用 pageComponents（WebSocket）
    const apiComponents = (page as any).components || []
    const wsComponents = pageComponents.value[page.id] || []
    
    // 如果API有数据就用API的，否则用WebSocket的
    pageComponents.value[page.id] = apiComponents.length > 0 ? apiComponents : wsComponents
  })'''

content = content.replace(old_code, new_code)

with open('client/src/views/ProjectDetail.vue', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ 前端已优化，现在优先使用页面树API返回的components字段')
