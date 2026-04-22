<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, h, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  CloudDownloadOutlined,
  HistoryOutlined,
  FileTextOutlined,
  LeftOutlined,
  RightOutlined,
  FileOutlined,
  RobotOutlined,
  VideoCameraOutlined,
  CopyOutlined,
} from '@ant-design/icons-vue'
import type { Project, TestPage } from '../types'
import { projectApi, pageApi, generateApi } from '../services/api'
import RecorderModal from '../components/RecorderModal.vue'

// Markdown 日志高亮控件
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)
const project = ref<Project | null>(null)
const loading = ref(false)
const cloneLoading = ref(false)
const mcpDiscoverLoading = ref(false)  // MCP 嗅探加载状态
const treeLoading = ref(false)

// 视图切换
const treeViewMode = ref<'pages' | 'components'>('pages')  // 页面/组件切换
const showLeftSidebar = ref(true)  // 左侧边栏是否展开

// 录制相关
const showRecorder = ref(false)  // 是否显示录制弹窗
const showCoverageReport = ref(false)  // 是否显示覆盖率报告
const coverageReport = ref<any>(null)  // 覆盖率报告数据

// 组件相关
const componentList = ref<any[]>([])  // 组件列表
const componentFramework = ref('')  // 框架类型
const componentEntryPoints = ref<string[]>([])  // 入口点

// 双向关联
const pageComponents = ref<Record<string, string[]>>({})  // 页面 → 组件
const componentPages = ref<Record<string, string[]>>({})  // 组件 → 页面
const selectedNodeId = ref<string | null>(null)
const checkedPageIds = ref<string[]>([])  // 复选的页面ID列表
const associationPanel = ref<{
  visible: boolean
  title: string
  type: 'page' | 'component'
  items: string[]
  description?: string  // 页面描述
  isCaptured?: boolean
  pageId?: string
}>({
  visible: false,
  title: '',
  type: 'page',
  items: [],
  description: '',
  isCaptured: false,
  pageId: ''
})

// 快照弹窗状态
const snapshotModal = ref({
  visible: false,
  pageId: ''
})

function showSnapshotModal(pageId?: string) {
  if (!pageId) return
  snapshotModal.value = {
    visible: true,
    pageId
  }
}

// 复制JSON内容
function copyToClipboard(text: string) {
  if (!text) return
  try {
    const rawText = JSON.stringify(JSON.parse(text), null, 2)
    navigator.clipboard.writeText(rawText).then(() => {
      message.success('已复制到剪贴板')
    }).catch(() => {
      message.error('复制失败，可能是浏览器权限限制')
    })
  } catch (e) {
    message.error('解析 JSON 数据失败')
  }
}

// 页面树相关
const pageTree = ref<TestPage[]>([])
const selectedPageId = ref<string | null>(null)
const treeExpandedKeys = ref<string[]>([])

// MCP日志相关
const showMCPLog = ref(false)  // 是否显示MCP日志面板
const mcpLogs = ref<any[]>([])  // MCP日志列表
const mcpLogWebSocket = ref<WebSocket | null>(null)  // WebSocket连接
const mcpIsRunning = ref(false)  // MCP是否正在运行
const mcpLogContainer = ref<HTMLElement | null>(null)  // 日志容器引用
const userScrolled = ref(false)  // 用户是否手动滚动了

// MCP日志等级图标
const logLevelIcons: Record<string, string> = {
  info: '💬',
  success: '✅',
  warning: '⚠️',
  error: '❌',
  debug: '🔍'
}

const activeTab = computed(() => {
  if (route.name === 'Executions') return 'executions'
  return 'cases'
})

async function loadProject() {
  loading.value = true
  try {
    project.value = await projectApi.get(projectId.value)
  } catch (e) {
    console.error('[ProjectDetail] 项目加载失败:', e)
  } finally {
    loading.value = false
  }
}

async function loadPageTree() {
  // 移除硬性 repo_path 检查，允许在未拉取代码时查看录制页面
  treeLoading.value = true
  try {
    const res = await pageApi.getTree(projectId.value)
    pageTree.value = res.pages
    
    // 递归获取所有节点ID，默认展开所有层级
    function getAllPageIds(pages: any[]): string[] {
      let ids = []
      for (const page of pages) {
        ids.push(page.id)
        if (page.children && page.children.length > 0) {
          ids = ids.concat(getAllPageIds(page.children))
        }
      }
      return ids
    }
    treeExpandedKeys.value = getAllPageIds(res.pages)
    
    // 加载完成后建立关联
    buildAssociations()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载页面树失败')
  } finally {
    treeLoading.value = false
  }
}

// 加载组件列表
async function loadComponents() {
  if (!project.value?.repo_path) {
    message.warning('请先拉取代码')
    return
  }
  
  treeLoading.value = true
  try {
    const res = await generateApi.getComponents(projectId.value)
    componentList.value = res.components
    componentFramework.value = res.framework
    componentEntryPoints.value = res.entry_points
    
    // 加载完成后建立关联
    buildAssociations()
    
    message.success(`发现 ${res.components.length} 个组件`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载组件列表失败')
  } finally {
    treeLoading.value = false
  }
}

// 录制完成回调
async function handleRecordingComplete(report: any) {
  if (!report || typeof report.coverage_rate === 'undefined') {
    await loadPageTree()
    return
  }

  coverageReport.value = report
  showCoverageReport.value = true
  
  // 确保数据已同步后刷新页面树
  await loadPageTree()
  
  // 延迟再次刷新，防止后端异步写入延迟
  setTimeout(async () => {
    await loadPageTree()
  }, 1000)
}

// 建立双向关联
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
  
  // 只使用MCP分析后的组件数据
  // 判断标准：component_name 是 JSON 数组格式（MCP分析结果），而不是对象格式（静态分析）
  allPages.forEach(page => {
    const componentName = page.component_name
    
    // 尝试解析 component_name
    let mcpComponents = []
    if (componentName) {
      try {
        const parsed = JSON.parse(componentName)
        // 如果是数组，说明是MCP分析结果
        if (Array.isArray(parsed)) {
          mcpComponents = parsed
        }
      } catch {
        // 解析失败，说明不是JSON格式
      }
    }
    
    // 只使用MCP分析的组件，没有就是空数组（显示为0）
    pageComponents.value[page.id] = mcpComponents
  })
  
  // 组件 → 页面（反向查找）
  componentList.value.forEach(comp => {
    const usedInPages: string[] = []
    allPages.forEach(page => {
      const pageComps = pageComponents.value[page.id] || []
      if (pageComps.includes(comp.name)) {
        usedInPages.push(page.name || comp.name)
      }
    })
    componentPages.value[comp.name] = usedInPages
  })
  
  console.log('[关联] 页面-组件关联建立完成')
}

// 滚动到底部
function scrollToBottom() {
  if (userScrolled.value) return  // 用户手动滚动时不自动滚动
  
  nextTick(() => {
    if (mcpLogContainer.value) {
      mcpLogContainer.value.scrollTop = mcpLogContainer.value.scrollHeight
    }
  })
}

// 监听用户滚动事件
function onMcpLogScroll() {
  if (!mcpLogContainer.value) return
  
  const { scrollTop, scrollHeight, clientHeight } = mcpLogContainer.value
  const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
  
  // 如果当前在底部，则标记为未手动滚动（允许自动跟随）
  // 如果离开底部，则标记为手动滚动（禁止自动跟随）
  userScrolled.value = !isAtBottom
}

// 处理树节点复选
function onTreeCheck(checkedKeys: any, _info: any) {
  // checkedKeys 可能是对象 {checked: [], halfChecked: []} 或数组
  let keys = []
  if (Array.isArray(checkedKeys)) {
    keys = checkedKeys
  } else if (checkedKeys && checkedKeys.checked) {
    keys = checkedKeys.checked
  }
  
  // 直接使用keys，因为a-tree的checked事件已经处理了级联逻辑
  // 我们只需要过滤掉文件夹的key（通过检查treeData判断）
  function getAllLeafKeys(nodes: any[]): string[] {
    let leafKeys: string[] = []
    for (const node of nodes) {
      if (node.isLeaf) {
        leafKeys.push(node.key)
      }
      if (node.children && node.children.length > 0) {
        leafKeys = leafKeys.concat(getAllLeafKeys(node.children))
      }
    }
    return leafKeys
  }
  
  const allLeafKeys = getAllLeafKeys(convertToTreeData(pageTree.value))
  // 只保留叶子节点的key
  checkedPageIds.value = keys.filter((k: string) => allLeafKeys.includes(k))
  
  // 立即更新路由参数，通知TestCaseList
  if (route.name === 'TestCases') {
    // 如果当前在用例页面，直接更新query
    router.replace({
      name: 'TestCases',
      params: { id: projectId.value },
      query: {
        ...route.query,
        page_ids: checkedPageIds.value.length > 0 ? checkedPageIds.value.join(',') : undefined
      }
    })

  }
}

// 显示关联信息面板
function showAssociationPanel(title: string, type: 'page' | 'component', items: any[], description?: string, isCaptured?: boolean, pageId?: string) {
  associationPanel.value = {
    visible: true,
    title,
    type,
    items,
    description: description || '',
    isCaptured: isCaptured || false,
    pageId: pageId || ''
  }
}

// 页面节点选择
async function onPageSelect(selectedKeys: string[], info: any) {
  // 递归查找页面
  function findPageInTree(pages: any[], pageId: string): any {
    for (const page of pages) {
      if (page.id === pageId) {
        return page
      }
      if (page.children && page.children.length > 0) {
        const found = findPageInTree(page.children, pageId)
        if (found) return found
      }
    }
    return null
  }
  
  // 尝试从 info 中获取节点信息
  const node = info?.node
  if (node) {
    const pageId = node.key
    const page = findPageInTree(pageTree.value, pageId)
    
    if (page) {
      selectedNodeId.value = pageId
      let traces = []
      try {
        traces = await pageApi.getTraces(pageId)
      } catch (e) {
        console.error('Failed to load traces', e)
      }
      
      showAssociationPanel(
        `页面: ${page.name || page.path}`,
        'page',
        traces,
        page.description,  // 传入description
        (page as any).is_captured,
        page.id
      )
      
      // 同时触发路由跳转，传递选中的页面IDs
      handlePageSelect(pageId, page)
      return
    }
  }
  
  // 备用方案：从 selectedKeys 获取
  if (selectedKeys.length > 0) {
    const pageId = selectedKeys[0]
    selectedNodeId.value = pageId
    const page = findPageInTree(pageTree.value, pageId)
    
    if (page) {
      let traces = []
      try {
        traces = await pageApi.getTraces(pageId)
      } catch (e) {
        console.error('Failed to load traces', e)
      }
      showAssociationPanel(
        `页面: ${page.name || page.path}`,
        'page',
        traces,
        page.description,
        (page as any).is_captured,
        page.id
      )
    }
  }
}

// 组件节点选择
function onComponentSelect(selectedKeys: string[], _info: any) {
  if (selectedKeys.length > 0) {
    const componentName = selectedKeys[0]
    selectedNodeId.value = componentName
    const pages = componentPages.value[componentName] || []
    
    showAssociationPanel(
      `组件: ${componentName}`,
      'component',
      pages
    )
  }
}

async function handleRefreshTree() {
  if (!project.value?.repo_path) {
    message.warning('请先拉取代码')
    return
  }
  
  treeLoading.value = true
  try {
    const res = await pageApi.refresh(projectId.value)
    message.success(res.message)
    pageTree.value = res.pages
    treeExpandedKeys.value = res.pages.map(p => p.id)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '刷新页面树失败')
  } finally {
    treeLoading.value = false
  }
}

async function handleClone() {
  cloneLoading.value = true
  try {
    const res = await projectApi.clone(projectId.value)
    await loadProject()
    
    // 显示成功弹窗，用户手动关闭
    Modal.success({
      title: '代码拉取成功',
      content: h('div', [
        h('p', res.message || '代码已成功拉取到本地'),
        h('p', { style: 'color: #999; font-size: 12px; margin-top: 8px;' }, 
          `存储路径: ${project.value?.repo_path || ''}`
        ),
      ]),
      okText: '知道了',
      onOk: () => {
        // 关闭弹窗后自动刷新页面树
        if (project.value?.repo_path) {
          handleRefreshTree()
        }
      },
    })
  } catch (e: any) {
    message.error(e.response?.data?.detail || '代码拉取失败')
  } finally {
    cloneLoading.value = false
  }
}

// WebSocket日志连接
let reconnectAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 3

function connectMCPLogWebSocket(): Promise<void> {
  return new Promise((resolve, _reject) => {
    if (mcpLogWebSocket.value) {
      mcpLogWebSocket.value.close()
    }
    
    // WebSocket应该连接到后端端口8004，而不是前端端口5173
    // 使用当前环境一致的端口
    const wsUrl = `ws://localhost:8004/ws/mcp/${projectId.value}`
    const ws = new WebSocket(wsUrl)
    
    ws.onopen = () => {
      reconnectAttempts = 0  // 重置重连计数
      resolve()  // 连接建立后通知
    }
    
    ws.onmessage = (event) => {
      try {
        const logEntry = JSON.parse(event.data)
        
        // 【优化】如果是流式内容(stream)，尝试合并到最后一条，防止大量换行和碎片化
        if (logEntry.level === 'stream' && mcpLogs.value.length > 0) {
          const lastLog = mcpLogs.value[mcpLogs.value.length - 1]
          if (lastLog.level === 'stream') {
            // 因为后端发送的是累计buffer，所以这里直接覆盖即可实现平滑增长
            lastLog.message = logEntry.message
            scrollToBottom()
            return
          }
        }

        mcpLogs.value.push({
          ...logEntry,
          id: Date.now() + Math.random()
        })
        
        // 自动滚动到底部 (受 userScrolled 锁控制)
        scrollToBottom()
          
        // 从日志中提取组件关联信息
      } catch (e) {
        console.error('解析MCP日志失败:', e)
      }
    }
    
    ws.onerror = (error) => {
      console.error('MCP日志WebSocket错误:', error)
    }
    
    ws.onclose = () => {
      console.log('MCP日志WebSocket已断开')
      mcpLogWebSocket.value = null
      
      // 自动重连（如果正在运行且未达到最大重连次数）
      if (mcpIsRunning.value && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++
        console.log(`WebSocket断开，${3}秒后尝试第${reconnectAttempts}次重连...`)
        setTimeout(() => {
          connectMCPLogWebSocket().catch(() => {
            console.log('WebSocket重连失败')
          })
        }, 3000)
      }
    }
    
    mcpLogWebSocket.value = ws
  })
}

function disconnectMCPLogWebSocket() {
  if (mcpLogWebSocket.value) {
    mcpLogWebSocket.value.close()
    mcpLogWebSocket.value = null
  }
}

function clearMCPLogs() {
  mcpLogs.value = []
}

async function handleMCPDiscover() {
  if (!project.value?.repo_path) {
    message.warning('请先拉取代码')
    return
  }
  
  // 清空之前的日志
  clearMCPLogs()
  // 标记为正在运行
  mcpIsRunning.value = true
  
  // 先建立WebSocket连接
  showMCPLog.value = true  // 打开面板
  await connectMCPLogWebSocket()  // 等待连接建立
  
  mcpDiscoverLoading.value = true
  try {
    const result = await generateApi.mcpDiscover(projectId.value)
    message.success(result.message || `MCP 嗅探完成，发现 ${result.page_count} 个页面`)
    
    // 刷新页面树
    await loadPageTree()
    
    // 自动加载组件列表，建立双向关联
    if (project.value?.repo_path) {
      await loadComponents()
    }
  } catch (e: any) {
    console.error('MCP 嗅探失败:', e)
    const errorMsg = e.response?.data?.detail || e.message || 'MCP 嗅探失败'
    message.error(errorMsg)
  } finally {
    mcpDiscoverLoading.value = false
    mcpIsRunning.value = false
  }
}

function handlePageSelect(pageId: string, page: TestPage) {
  if (page.is_leaf) {
    selectedPageId.value = pageId
    // 触发子组件加载该页面的用例
    const query: any = { 
      page_id: pageId,
      page_path: page.full_path,
    }
    
    // 如果有复选的页面，也传递过去
    if (checkedPageIds.value.length > 0) {
      query.page_ids = checkedPageIds.value.join(',')
    }
    router.push({ 
      name: 'TestCases', 
      params: { id: projectId.value }, 
      query
    })
  }
}

function switchTab(key: string) {
  if (key === 'executions') {
    router.push(`/project/${projectId.value}/executions`)
  } else {
    router.push(`/project/${projectId.value}`)
  }
}

// 过滤页面树：仅显示已录制的页面
const capturedPages = computed(() => {
  // 递归筛选出 is_captured 的叶子节点，或者包含 captured 节点的父节点
  function filterCaptured(pages: TestPage[]): TestPage[] {
    return pages
      .map(p => ({ ...p }))
      .filter(p => {
        if (p.is_leaf) {
          return (p as any).is_captured
        }
        if (p.children) {
          p.children = filterCaptured(p.children)
          return p.children.length > 0
        }
        return false
      })
  }
  return filterCaptured(pageTree.value)
})

// 将页面树转换为 a-tree 需要的数据格式
function convertToTreeData(pages: TestPage[]): any[] {
  return pages.map(page => ({
    key: page.id,
    title: (page as any).is_captured ? `📹 ${page.full_path}` : (page.name || page.path),
    fullPath: page.full_path,
    description: page.description || '',
    icon: page.is_leaf ? FileOutlined : RightOutlined,
    children: page.children ? convertToTreeData(page.children) : [],
    isLeaf: page.is_leaf,
    isCaptured: (page as any).is_captured,
  }))
}

onMounted(async () => {
  await loadProject()
  // 如果已拉取代码，自动加载页面树
  if (project.value?.repo_path) {
    await loadPageTree()
  }
  // 连接WebSocket接收MCP日志
  connectMCPLogWebSocket().catch(err => {
    console.error('WebSocket连接失败:', err)
  })
})

onUnmounted(() => {
  disconnectMCPLogWebSocket()
})
</script>

<template>
  <div style="position: relative;">
    <!-- 右侧MCP日志浮动按钮 - 始终显示，有日志时显示数量 -->
    <div 
      style="position: fixed; right: 16px; top: 50%; transform: translateY(-50%); z-index: 1000;"
    >
      <a-badge :count="mcpLogs.length > 0 ? mcpLogs.length : undefined" :overflow-count="99" :number-style="{ backgroundColor: mcpIsRunning ? '#1890ff' : '#52c41a' }">
        <a-button 
          type="primary" 
          shape="circle" 
          size="large"
          @click="showMCPLog = !showMCPLog"
          :icon="h(RobotOutlined)"
          style="box-shadow: 0 4px 12px rgba(0,0,0,0.15);"
        />
      </a-badge>
    </div>
    
    <a-page-header
      :title="project?.name || '加载中...'"
      :sub-title="project?.base_url"
      @back="router.push('/projects')"
    >
      <template #extra>
        <a-space>
          <a-button @click="handleClone" :loading="cloneLoading">
            <CloudDownloadOutlined /> {{ project?.repo_path ? '重新拉取' : '拉取代码' }}
          </a-button>
          <a-button 
            type="primary" 
            @click="handleMCPDiscover" 
            :loading="mcpDiscoverLoading"
          >
            <RobotOutlined /> MCP 页面嗅探
          </a-button>
        </a-space>
      </template>
      <a-descriptions size="small" :column="3" v-if="project">
        <a-descriptions-item label="Git 仓库">{{ project.git_url }}</a-descriptions-item>
        <a-descriptions-item label="分支">{{ project.branch }}</a-descriptions-item>
        <a-descriptions-item label="代码状态">
          <a-tag :color="project.repo_path ? 'green' : 'orange'">
            {{ project.repo_path ? '已拉取' : '未拉取' }}
          </a-tag>
        </a-descriptions-item>
      </a-descriptions>
    </a-page-header>

    <div style="display: flex; gap: 16px; margin-top: 16px;">
      <!-- 展开侧边栏按钮（收起时显示） -->
      <a-button 
        v-show="!showLeftSidebar"
        type="primary" 
        @click="showLeftSidebar = true"
        style="width: 32px; flex-shrink: 0; height: auto; padding: 8px 0;"
      >
        <RightOutlined />
      </a-button>
      
      <!-- 左侧页面树/组件树 -->
      <a-card 
        v-show="showLeftSidebar"
        :title="treeViewMode === 'pages' ? '页面列表' : '组件列表'" 
        :bordered="true" 
        style="width: 300px; flex-shrink: 0;"
        :bodyStyle="{ padding: '12px' }"
      >
        <template #extra>
          <a-space>
            <!-- 探索录制按钮 -->
            <a-button 
              type="primary" 
              size="small"
              @click="showRecorder = true"
            >
              <template #icon><VideoCameraOutlined /></template>
              探索录制
            </a-button>
            
            <!-- 刷新页面树按钮 -->
            <a-button 
              type="text" 
              size="small" 
              @click="handleRefreshTree"
              :loading="treeLoading"
              title="刷新页面树"
            >
              🔄
            </a-button>
            
            <!-- 折叠按钮 -->
            <a-button 
              type="text" 
              size="small" 
              @click="showLeftSidebar = false"
              style="padding: 4px;"
            >
              <LeftOutlined />
            </a-button>
            
            <!-- 视图切换 -->
            <a-radio-group v-model:value="treeViewMode" button-style="solid" size="small">
              <a-radio-button value="pages">页面</a-radio-button>
              <a-radio-button value="components">组件</a-radio-button>
            </a-radio-group>
          </a-space>
        </template>
        

        
        <!-- 页面树模式 -->
        <div v-if="treeViewMode === 'pages'">
          <div v-if="capturedPages.length === 0" style="padding: 20px; text-align: center; color: #999;">
            暂无录制页面，请点击上方“探索录制”
          </div>
          
          <a-tree
            v-else
            :tree-data="convertToTreeData(capturedPages)"
            :expanded-keys="treeExpandedKeys"
            @expand="(keys: string[]) => treeExpandedKeys = keys"
            @select="onPageSelect"
            :selected-keys="selectedNodeId ? [selectedNodeId] : []"
            :show-line="true"
            checkable
            :checked-keys="{ checked: checkedPageIds, halfChecked: [] }"
            @check="onTreeCheck"
          >
            <template #title="{ dataRef }">
              <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                <span>{{ dataRef.title }}</span>
                  <!-- 显示录制轨迹数量 -->
                  <a-badge 
                    v-if="dataRef.isLeaf"
                    :count="0" 
                    :number-style="{ backgroundColor: '#52c41a' }"
                    size="small"
                    title="录制轨迹数量"
                  />
              </div>
            </template>
          </a-tree>
        </div>
        
        <!-- 组件树模式 -->
        <div v-else>
          <div v-if="componentList.length === 0" style="padding: 20px; text-align: center; color: #999;">
            <a-button type="link" @click="loadComponents">点击加载组件列表</a-button>
          </div>
          
          <a-tree
            v-else
            :tree-data="componentList.map(c => ({
              key: c.name,
              title: c.name,
              isLeaf: true,
            }))"
            @select="onComponentSelect"
            :selected-keys="selectedNodeId ? [selectedNodeId] : []"
            :show-line="true"
          >
            <template #title="{ dataRef }">
              <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                <span>{{ dataRef.title }}</span>
                <a-tag size="small" color="green">
                  {{ componentPages[dataRef.key]?.length || 0 }} 个页面
                </a-tag>
              </div>
            </template>
          </a-tree>
        </div>
      </a-card>
      
      <!-- 关联信息浮动窗口 -->
      <a-modal
        v-model:open="associationPanel.visible"
        :title="associationPanel.title"
        :footer="null"
        width="600px"
        :bodyStyle="{ maxHeight: '70vh', overflowY: 'auto' }"
      >
        <!-- 页面录制成果展示 -->
        <div v-if="associationPanel.type === 'page'">
          <div v-if="associationPanel.items && associationPanel.items.length > 0">
            <div v-for="(trace, index) in associationPanel.items" :key="trace.id" style="margin-bottom: 16px; border: 1px solid #ebedf0; border-radius: 4px; padding: 12px;">
              <div style="font-weight: bold; margin-bottom: 8px; color: #1890ff;">{{ trace.title }}</div>
              <div style="color: #666; font-size: 12px; margin-bottom: 12px;">{{ trace.description }}</div>
              <div style="position: relative; background: #1e1e1e; padding: 12px; border-radius: 4px; overflow-x: auto; max-height: 400px; overflow-y: auto;">
                <a-button 
                  v-if="trace.trace_data"
                  type="text" 
                  size="small" 
                  style="position: absolute; top: 8px; right: 8px; color: #999; background: rgba(255,255,255,0.1);"
                  @click="copyToClipboard(trace.trace_data)"
                  title="复制全量 JSON"
                >
                  <CopyOutlined /> 复制
                </a-button>
                <pre style="margin: 0; color: #d4d4d4; font-family: 'SF Mono', Consolas, monospace; font-size: 12px;">{{ trace.trace_data ? JSON.stringify(JSON.parse(trace.trace_data), null, 2) : '暂无数据' }}</pre>
              </div>
            </div>
          </div>
          <div v-else style="padding: 20px; text-align: center; color: #999;">
            此页面暂无关联的录制轨迹数据
          </div>
        </div>
        
        <!-- 组件对应的页面列表 -->
        <div v-if="associationPanel.type === 'component'">
          <div style="font-weight: 500; margin-bottom: 8px; color: #666; font-size: 12px;">📄 使用的页面</div>
          <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            <a-tag 
              v-for="page in associationPanel.items" 
              :key="page"
              color="green"
            >
              {{ page }}
            </a-tag>
            <span v-if="associationPanel.items.length === 0" style="color: #999; font-size: 13px; font-style: italic;">
              暂无页面使用此组件
            </span>
          </div>
        </div>
      </a-modal>

      <!-- 右侧用例列表 -->
      <a-card style="flex: 1;" :bordered="false" :bodyStyle="{ padding: '0' }">
        <a-tabs :activeKey="activeTab" @change="switchTab">
          <a-tab-pane key="cases">
            <template #tab><FileTextOutlined /> 测试用例</template>
          </a-tab-pane>
          <a-tab-pane key="executions">
            <template #tab><HistoryOutlined /> 执行历史</template>
          </a-tab-pane>
        </a-tabs>

        <div style="padding: 16px;">
          <router-view 
            :key="route.fullPath" 
            @open-mcp-log="showMCPLog = true" 
            @clear-mcp-log="clearMCPLogs" 
            @set-mcp-running="mcpIsRunning = $event" 
          />
        </div>
      </a-card>
    </div>
    
    <!-- MCP实时日志面板 - 右侧展开 -->
    <a-drawer
      v-model:open="showMCPLog"
      title="🤖 MCP 分析日志"
      placement="right"
      :width="500"
      :closable="true"
    >
      <template #extra>
        <a-space>
          <a-button size="small" @click="clearMCPLogs">清空日志</a-button>
          <a-tag>{{ mcpLogs.length }} 条日志</a-tag>
        </a-space>
      </template>
      
      <!-- MCP日志容器 -->
      <div 
        ref="mcpLogContainer"
        class="mcp-log-content" 
        @scroll="onMcpLogScroll"
        style="height: calc(100vh - 120px); overflow-y: auto; font-family: 'SF Mono', 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 12px; background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px;"
      >
        <div v-if="mcpLogs.length === 0" style="color: #666; text-align: center; padding: 40px;">
          等待日志输出...
        </div>
        
        <!-- 日志消息列表 -->
        <div 
          v-for="log in mcpLogs" 
          :key="log.id"
          class="log-message"
        >
          <!-- 普通日志：显示时间戳和图标 -->
          <template v-if="log.level !== 'stream'">
            <div class="log-header">
              <span class="log-time">{{ log.timestamp?.split('T')[1]?.split('.')[0] || '' }}</span>
              <span class="log-icon">{{ logLevelIcons[log.level] || '📝' }}</span>
            </div>
            <div class="log-body">
              {{ log.message }}
            </div>
          </template>
          
          <!-- 流式内容：基于成型的 Markdown 渲染控件呈现 -->
          <div v-else class="log-body log-stream mcp-md-overrides">
            <MdPreview 
              :modelValue="log.message" 
              theme="dark" 
              previewTheme="github"
              codeTheme="github"
            />
          </div>
          
          <!-- 附加数据 -->
          <div v-if="log.data" class="log-data">
            {{ JSON.stringify(log.data, null, 2) }}
          </div>
        </div>
      </div>
    </a-drawer>
    
    <!-- 录制弹窗 -->
    <RecorderModal 
      v-model:open="showRecorder"
      :project-id="project?.id"
      @recording-complete="handleRecordingComplete"
    />
    
    <!-- DOM 快照预览弹窗 -->
    <a-modal
      v-model:open="snapshotModal.visible"
      title="🖼️ 页面 DOM 快照"
      width="90%"
      :footer="null"
      :bodyStyle="{ padding: 0, height: '80vh' }"
      destroyOnClose
    >
      <iframe 
        v-if="snapshotModal.visible"
        :src="`/api/recording/${projectId}/pages/${snapshotModal.pageId}/snapshot`"
        style="width: 100%; height: 100%; border: none"
        sandbox=""
      />
    </a-modal>
    
    <!-- 覆盖率报告弹窗 -->
    <a-modal
      v-model:open="showCoverageReport"
      title="📊 录制覆盖率分析"
      :width="800"
      :maskClosable="false"
      :closable="false"
      :footer="null"
      @cancel="loadPageTree"
    >
      <a-result
        v-if="coverageReport"
        :status="coverageReport.coverage_rate >= 0.8 ? 'success' : 'warning'"
        :title="`覆盖率 ${(coverageReport.coverage_rate * 100).toFixed(1)}%`"
        :sub-title="`已录制 ${coverageReport.recorded_count} 个页面，遗漏 ${coverageReport.missed_count} 个页面`"
      >
        <template #extra>
          <a-space>
            <a-button type="primary" @click="showCoverageReport = false; showRecorder = true; loadPageTree()">
              继续录制
            </a-button>
            <a-button @click="showCoverageReport = false; loadPageTree()">
              确定
            </a-button>
          </a-space>
        </template>
      </a-result>

      <!-- 遗漏页面列表 -->
      <a-collapse v-if="coverageReport && coverageReport.missed_pages && coverageReport.missed_pages.length > 0">
        <a-collapse-panel key="high" header="🔴 高优先级遗漏（建议录制）">
          <a-list 
            :data-source="coverageReport.missed_pages.filter((p: any) => p.priority === 'high')"
            size="small"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="red">{{ item.type }}</a-tag>
                {{ item.pattern }}
              </a-list-item>
            </template>
          </a-list>
        </a-collapse-panel>

        <a-collapse-panel key="medium" header="🟡 中优先级遗漏（建议录制）">
          <a-list 
            :data-source="coverageReport.missed_pages.filter((p: any) => p.priority === 'medium')"
            size="small"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="orange">{{ item.type }}</a-tag>
                {{ item.pattern }}
              </a-list-item>
            </template>
          </a-list>
        </a-collapse-panel>

        <a-collapse-panel key="low" header="🟢 低优先级遗漏（可选）">
          <a-list 
            :data-source="coverageReport.missed_pages.filter((p: any) => p.priority === 'low')"
            size="small"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="green">{{ item.type }}</a-tag>
                {{ item.pattern }}
              </a-list-item>
            </template>
          </a-list>
        </a-collapse-panel>
      </a-collapse>
      
      <!-- 建议 -->
      <a-alert
        v-if="coverageReport && coverageReport.suggestions && coverageReport.suggestions.length > 0"
        type="info"
        :message="coverageReport.suggestions"
        show-icon
        style="margin-top: 16px"
      />
    </a-modal>
  </div>
</template>

<style scoped>
/* 日志消息容器 */
.log-message {
  margin-bottom: 12px;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  line-height: 1.5;
}

/* 日志头部（时间戳 + 图标） */
.log-header {
  margin-bottom: 4px;
  color: #888;
  font-size: 11px;
}

.log-time {
  margin-right: 8px;
}

.log-icon {
  margin-right: 6px;
}

/* 日志主体内容 */
.log-body {
  color: #d4d4d4;
  margin-left: 28px;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  line-height: 1.5;
}

/* 流式日志（LLM输出） */
.log-stream {
  color: #d4d4d4;
}

/* 附加数据（JSON） */
.log-data {
  margin-left: 28px;
  color: #6a9955;
  font-size: 11px;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  line-height: 1.4;
}

/* 覆盖底层控件防止出现黑底白边，融入黑金背板 */
:deep(.mcp-md-overrides .md-editor-previewOnly) {
  background-color: transparent !important;
}
:deep(.mcp-md-overrides .md-editor-preview-wrapper) {
  padding: 0 !important;
}
:deep(.mcp-md-overrides .default-theme p) {
  color: #d4d4d4 !important;
  margin-bottom: 8px;
}

/* 强化代码注释，方便非开发者快速阅读意图 */
:deep(.mcp-md-overrides .hljs-comment) {
  color: #10b981 !important;
  font-style: normal !important;
  font-weight: 500 !important;
}
</style>
