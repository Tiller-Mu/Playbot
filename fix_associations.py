import re

with open('client/src/views/ProjectDetail.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复 buildAssociations 函数，添加递归收集所有页面
old_func = '''// 建立双向关联
function buildAssociations() {
  // 如果pageComponents已经有数据（从WebSocket收到的），直接使用
  // 否则从页面树数据中获取
  pageTree.value.forEach(page => {
    // pageComponents中如果有数据就使用，没有就设为空数组
    if (!pageComponents.value[page.id]) {
      const components = (page as any).components || []
      pageComponents.value[page.id] = components
    }
  })
  
  // 组件 → 页面（反向查找）
  componentList.value.forEach(comp => {
    const usedInPages: string[] = []
    pageTree.value.forEach(page => {'''

new_func = '''// 建立双向关联
function buildAssociations() {
  // 递归收集所有页面
  function collectAllPages(pages: any[]): any[] {
    let allPages: any[] = []
    for (const page of pages) {
      allPages.push(page)
      if (page.children && page.children.length > 0) {
        allPages = allPages.concat(collectAllPages(page.children))
      }
    }
    return allPages
  }
  
  const allPages = collectAllPages(pageTree.value)
  
  // 如果pageComponents已经有数据（从WebSocket收到的），直接使用
  // 否则从页面树数据中获取
  allPages.forEach(page => {
    // pageComponents中如果有数据就使用，没有就设为空数组
    if (!pageComponents.value[page.id]) {
      const components = (page as any).components || []
      pageComponents.value[page.id] = components
    }
  })
  
  // 组件 → 页面（反向查找）
  componentList.value.forEach(comp => {
    const usedInPages: string[] = []
    allPages.forEach(page => {'''

content = content.replace(old_func, new_func)

with open('client/src/views/ProjectDetail.vue', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ buildAssociations 函数已修复，支持递归遍历所有页面')
