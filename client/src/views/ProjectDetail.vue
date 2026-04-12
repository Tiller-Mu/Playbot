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
} from '@ant-design/icons-vue'
import type { Project, TestPage } from '../types'
import { projectApi, pageApi, generateApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)
const project = ref<Project | null>(null)
const loading = ref(false)
const cloneLoading = ref(false)
const mcpDiscoverLoading = ref(false)  // MCP 嗅探加载状态
const treeLoading = ref(false)
const pageGenerating = ref<Record<string, boolean>>({})  // 记录每个页面的生成状态

// 视图切换
const treeViewMode = ref<'pages' | 'components'>('pages')  // 页面/组件切换
const showLeftSidebar = ref(false)  // 左侧边栏是否展开

// 组件相关
const componentList = ref<any[]>([])  // 组件列表
const componentFramework = ref('')  // 框架类型
const componentEntryPoints = ref<string[]>([])  // 入口点

// 双向关联
const pageComponents = ref<Record<string, string[]>>({})  // 页面 → 组件
const componentPages = ref<Record<string, string[]>>({})  // 组件 → 页面
const selectedNodeId = ref<string | null>(null)
const associationPanel = ref<{
  visible: boolean
  title: string
  type: 'page' | 'component'
  items: string[]
  description?: string  // 页面描述
}>({
  visible: false,
  title: '',
  type: 'page',
  items: [],
  description: ''
})

// 页面树相关
const pageTree = ref<TestPage[]>([])
const selectedPageId = ref<string | null>(null)
const treeExpandedKeys = ref<string[]>([])
const analyzingPages = ref<Record<string, boolean>>({})  // 记录每个页面的分析状态

// MCP日志相关
const showMCPLog = ref(false)  // 是否显示MCP日志面板
const mcpLogs = ref<any[]>([])  // MCP日志列表
const mcpLogWebSocket = ref<WebSocket | null>(null)  // WebSocket连接
const mcpIsRunning = ref(false)  // MCP是否正在运行

// MCP日志等级图标
const logLevelIcons: Record<string, string> = {
  info: '💬',
  success: '✅',
  warning: '⚠️',
  error: '❌',
  debug: '🔍'
}

// MCP日志等级颜色
const logLevelColors: Record<string, string> = {
  info: '#1890ff',
  success: '#52c41a',
  warning: '#faad14',
  error: '#ff4d4f',
  debug: '#8c8c8c'
}

const activeTab = computed(() => {
  if (route.name === 'Executions') return 'executions'
  return 'cases'
})

async function loadProject() {
  console.log('[ProjectDetail] 开始加载项目, projectId:', projectId.value)
  loading.value = true
  try {
    project.value = await projectApi.get(projectId.value)
    console.log('[ProjectDetail] 项目加载成功:', project.value?.name)
  } catch (e) {
    console.error('[ProjectDetail] 项目加载失败:', e)
  } finally {
    loading.value = false
    console.log('[ProjectDetail] loading设置为false, project:', project.value?.name)
  }
}

async function loadPageTree() {
  if (!project.value?.repo_path) {
    message.warning('请先拉取代码')
    return
  }
  
  treeLoading.value = true
  try {
    const res = await pageApi.getTree(projectId.value)
    pageTree.value = res.pages
    
    // 默认展开第一层
    treeExpandedKeys.value = res.pages.map(p => p.id)
    
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

// 建立双向关联
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
    pageTree.value.forEach(page => {
      const pageComps = pageComponents.value[page.id] || []
      if (pageComps.includes(comp.name)) {
        usedInPages.push(page.name || comp.name)
      }
    })
    componentPages.value[comp.name] = usedInPages
  })
  
  console.log('[关联] pageComponents:', pageComponents.value)
  console.log('[关联] componentPages:', componentPages.value)
}

// 显示关联信息面板
function showAssociationPanel(title: string, type: 'page' | 'component', items: string[], description?: string) {
  associationPanel.value = {
    visible: true,
    title,
    type,
    items,
    description: description || ''
  }
}

// 页面节点选择
function onPageSelect(selectedKeys: string[], info: any) {
  console.log('[onPageSelect] 被调用, selectedKeys:', selectedKeys)
  console.log('[onPageSelect] info.node:', info?.node)
  console.log('[onPageSelect] info.node.key:', info?.node?.key)
  
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
    
    console.log('[onPageSelect] 从info找到的页面:', page)
    console.log('[onPageSelect] 页面的description:', page.description)
    console.log('[onPageSelect] 页面完整数据:', JSON.stringify(page, null, 2))
    
    if (page) {
      selectedNodeId.value = pageId
      const components = pageComponents.value[pageId] || []
      console.log('[onPageSelect] 组件列表:', components)
      console.log('[onPageSelect] 页面描述:', page.description)
      
      showAssociationPanel(
        `页面: ${page.name || page.path}`,
        'page',
        components,
        page.description  // 传入description
      )
      
      console.log('[onPageSelect] 面板状态:', associationPanel.value)
      return
    }
  }
  
  // 备用方案：从 selectedKeys 获取
  if (selectedKeys.length > 0) {
    const pageId = selectedKeys[0]
    selectedNodeId.value = pageId
    const page = findPageInTree(pageTree.value, pageId)
    
    if (page) {
      const components = pageComponents.value[pageId] || []
      showAssociationPanel(
        `页面: ${page.name || page.path}`,
        'page',
        components,
        page.description
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

// 单页 LLM 分析
async function handleAnalyzePage(pageId: string) {
  if (analyzingPages.value[pageId]) return
  
  analyzingPages.value[pageId] = true
  showMCPLog.value = true  // 自动展开日志面板
  
  // 确保 WebSocket 已连接
  console.log('[handleAnalyzePage] WebSocket状态:', mcpLogWebSocket.value?.readyState)
  if (!mcpLogWebSocket.value || mcpLogWebSocket.value.readyState !== WebSocket.OPEN) {
    console.log('[handleAnalyzePage] 重新连接WebSocket...')
    try {
      await connectMCPLogWebSocket()
      console.log('[handleAnalyzePage] WebSocket已连接')
    } catch (e) {
      console.error('[handleAnalyzePage] WebSocket连接失败:', e)
    }
  } else {
    console.log('[handleAnalyzePage] WebSocket已连接，直接使用')
  }
  
  try {
    const result = await generateApi.analyzePage(pageId)
    
    message.success('页面分析完成')
    
    // 刷新页面树以显示新的描述
    await loadPageTree()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '页面分析失败')
  } finally {
    analyzingPages.value[pageId] = false
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
  return new Promise((resolve, reject) => {
    if (mcpLogWebSocket.value) {
      mcpLogWebSocket.value.close()
    }
    
    // WebSocket应该连接到后端端口8001，而不是前端端口5173
    // 使用当前API地址的端口
    const apiBaseURL = 'http://localhost:8003/api'
    const wsPort = apiBaseURL.match(/:(\d+)/)?.[1] || '8003'
    const wsUrl = `ws://localhost:${wsPort}/ws/mcp/${projectId.value}`
    console.log('连接MCP日志WebSocket:', wsUrl)
    const ws = new WebSocket(wsUrl)
    
    ws.onopen = () => {
      console.log('MCP日志WebSocket已连接')
      reconnectAttempts = 0  // 重置重连计数
      resolve()  // 连接建立后通知
    }
    
    ws.onmessage = (event) => {
      console.log('[WebSocket收到消息]', event.data)
      try {
        const logEntry = JSON.parse(event.data)
        console.log('[WebSocket解析后]', logEntry)
        mcpLogs.value.push({
          ...logEntry,
          id: Date.now() + Math.random()
        })
          
        // 从日志中提取组件关联信息
        if (logEntry.data?.components && logEntry.data?.route) {
          const route = logEntry.data.route
          const components = logEntry.data.components
          // 找到对应的页面
          const page = pageTree.value.find(p => p.full_path === route || p.path === route)
          if (page) {
            pageComponents.value[page.id] = components
            // 同时更新componentPages（组件→页面反向映射）
            components.forEach((compName: string) => {
              if (!componentPages.value[compName]) {
                componentPages.value[compName] = []
              }
              if (!componentPages.value[compName].includes(page.name || route)) {
                componentPages.value[compName].push(page.name || route)
              }
            })
          }
        }
          
        // 自动滚动到底部
        nextTick(() => {
          const logContainer = document.querySelector('.mcp-log-content')
          if (logContainer) {
            logContainer.scrollTop = logContainer.scrollHeight
          }
        })
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
  console.log('WebSocket连接已建立，开始调用API...')
  
  console.log('=== MCP 嗅探调试信息 ===')
  console.log('Project ID:', projectId.value)
  console.log('Repo Path:', project.value.repo_path)
  console.log('Base URL:', project.value.base_url)
  
  // 直接开始分析，不再弹出确认对话框（日志面板已经打开）
  mcpDiscoverLoading.value = true
  try {
    console.log('开始调用 MCP 嗅探 API...')
    const result = await generateApi.mcpDiscover(projectId.value)
    console.log('MCP 嗅探结果:', result)
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
    router.push({ 
      name: 'TestCases', 
      params: { id: projectId.value }, 
      query: { 
        page_id: pageId,
        page_path: page.full_path,
      }
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

// 将页面树转换为 a-tree 需要的数据格式
function convertToTreeData(pages: TestPage[]): any[] {
  return pages.map(page => ({
    key: page.id,
    title: page.name,
    description: page.description || '',  // 保留description供面板使用
    icon: page.is_leaf ? FileOutlined : RightOutlined,
    children: page.children ? convertToTreeData(page.children) : [],
    isLeaf: page.is_leaf,
  }))
}

onMounted(async () => {
  await loadProject()
  // 如果已拉取代码，自动加载页面树
  if (project.value?.repo_path) {
    await loadPageTree()
  }
})

onUnmounted(() => {
  disconnectMCPLogWebSocket()
})
</script>

<template>
  <div style="position: relative;">
    <!-- 右侧MCP日志浮动按钮 - 只要有日志历史或正在运行就显示 -->
    <div 
      v-if="mcpLogs.length > 0 || mcpIsRunning"
      style="position: fixed; right: 16px; top: 50%; transform: translateY(-50%); z-index: 1000;"
    >
      <a-badge :count="mcpLogs.length" :overflow-count="99" :number-style="{ backgroundColor: mcpIsRunning ? '#1890ff' : '#52c41a' }">
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
          <div v-if="!project?.repo_path" style="padding: 20px; text-align: center; color: #999;">
            请先拉取代码
          </div>
          
          <a-tree
            v-else
            :tree-data="convertToTreeData(pageTree)"
            :expanded-keys="treeExpandedKeys"
            @expand="(keys: string[]) => treeExpandedKeys = keys"
            @select="onPageSelect"
            :selected-keys="selectedNodeId ? [selectedNodeId] : []"
            :show-line="true"
          >
            <template #title="{ dataRef }">
              <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                <span>{{ dataRef.title }}</span>
                <div style="display: flex; gap: 4px;">
                  <a-tag size="small" :color="dataRef.isLeaf ? 'blue' : 'green'">
                    {{ dataRef.isLeaf ? `${pageComponents[dataRef.key]?.length || 0} 个组件` : '文件夹' }}
                  </a-tag>
                  <a-button 
                    v-if="dataRef.isLeaf"
                    size="small" 
                    type="link" 
                    :loading="analyzingPages[dataRef.key]"
                    @click.stop="handleAnalyzePage(dataRef.key)"
                    style="padding: 0 4px;"
                  >
                    🔍
                  </a-button>
                </div>
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
      
      <!-- 关联信息面板 -->
      <a-card 
        v-if="associationPanel.visible" 
        :title="associationPanel.title" 
        :bordered="true" 
        style="width: 350px; flex-shrink: 0;"
        :bodyStyle="{ padding: '12px' }"
        :closable="true"
        @close="associationPanel.visible = false"
      >
        <template #extra>
          <a-button 
            type="text" 
            size="small" 
            @click="associationPanel.visible = false"
            style="padding: 4px;"
          >
            关闭
          </a-button>
        </template>
        
        <!-- 页面描述 -->
        <div v-if="associationPanel.type === 'page'" 
             style="margin-bottom: 16px; padding: 12px; background: #f5f5f5; border-radius: 4px;">
          <div style="font-weight: 500; margin-bottom: 8px; color: #666; font-size: 12px;">📝 页面描述</div>
          <div v-if="associationPanel.description" style="color: #333; line-height: 1.6; font-size: 14px;">
            {{ associationPanel.description }}
          </div>
          <div v-else style="color: #999; font-size: 13px; font-style: italic;">
            暂无描述，点击右侧 🔍 按钮进行页面分析
          </div>
        </div>
        
        <!-- 关联列表 -->
        <div style="font-weight: 500; margin-bottom: 8px; color: #666; font-size: 12px;">
          {{ associationPanel.type === 'page' ? '🧩 使用的组件' : '📄 使用的页面' }}
        </div>
        <a-list 
          :data-source="associationPanel.items" 
          size="small"
          :locale="{ emptyText: associationPanel.type === 'page' ? '暂无组件关联，请先进行页面分析' : '暂无页面使用此组件' }"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-tag :color="associationPanel.type === 'page' ? 'blue' : 'green'">
                {{ item }}
              </a-tag>
            </a-list-item>
          </template>
        </a-list>
      </a-card>

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
          <router-view :key="route.fullPath" />
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
      
      <div class="mcp-log-content" style="height: calc(100vh - 120px); overflow-y: auto; font-family: 'Monaco', 'Menlo', monospace; font-size: 12px; background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px;">
        <div v-if="mcpLogs.length === 0" style="color: #666; text-align: center; padding: 40px;">
          等待日志输出...
        </div>
        <div 
          v-for="log in mcpLogs" 
          :key="log.id"
          style="margin-bottom: 6px; line-height: 1.5;"
        >
          <span style="color: #888;">{{ log.timestamp?.split('T')[1]?.split('.')[0] || '' }}</span>
          <span style="margin: 0 6px;">{{ logLevelIcons[log.level] || '📝' }}</span>
          <span :style="{ color: logLevelColors[log.level] || '#d4d4d4' }">{{ log.message }}</span>
          <div v-if="log.data" style="margin-left: 80px; color: #6a9955; font-size: 11px;">
            {{ JSON.stringify(log.data, null, 2) }}
          </div>
        </div>
      </div>
    </a-drawer>
  </div>
</template>
