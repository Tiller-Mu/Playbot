<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  CloudDownloadOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  FileTextOutlined,
  ReloadOutlined,
  LeftOutlined,
  RightOutlined,
  FileOutlined,
  RobotOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import type { Project, TestPage } from '../types'
import { projectApi, pageApi, generateApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)
const project = ref<Project | null>(null)
const loading = ref(false)
const cloneLoading = ref(false)
const generateLoading = ref(false)
const mcpGenerateLoading = ref(false)
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
}>({
  visible: false,
  title: '',
  type: 'page',
  items: []
})

// 页面树相关
const pageTree = ref<TestPage[]>([])
const selectedPageId = ref<string | null>(null)
const treeExpandedKeys = ref<string[]>([])

const activeTab = computed(() => {
  if (route.name === 'Executions') return 'executions'
  return 'cases'
})

async function loadProject() {
  loading.value = true
  try {
    project.value = await projectApi.get(projectId.value)
  } finally {
    loading.value = false
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
  // 页面 → 组件（从页面树数据中获取）
  pageTree.value.forEach(page => {
    // 从页面的 components 字段获取（如果有）
    const components = (page as any).components || []
    pageComponents.value[page.id] = components
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
}

// 显示关联信息面板
function showAssociationPanel(title: string, type: 'page' | 'component', items: string[]) {
  associationPanel.value = {
    visible: true,
    title,
    type,
    items
  }
}

// 页面节点选择
function onPageSelect(selectedKeys: string[], info: any) {
  if (selectedKeys.length > 0) {
    const pageId = selectedKeys[0]
    selectedNodeId.value = pageId
    const page = pageTree.value.find(p => p.id === pageId)
    
    if (page) {
      const components = pageComponents.value[pageId] || []
      showAssociationPanel(
        `页面: ${page.name || page.path}`,
        'page',
        components
      )
    }
  }
}

// 组件节点选择
function onComponentSelect(selectedKeys: string[], info: any) {
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

async function handleMCPDiscover() {
  if (!project.value?.repo_path) {
    message.warning('请先拉取代码')
    return
  }
  
  console.log('=== MCP 嗅探调试信息 ===')
  console.log('Project ID:', projectId.value)
  console.log('Repo Path:', project.value.repo_path)
  console.log('Base URL:', project.value.base_url)
  
  Modal.confirm({
    title: 'MCP 页面嗅探',
    content: h('div', [
      h('p', 'MCP 将通过静态代码分析发现所有页面。'),
      h('p', { style: 'color: #faad14; font-size: 12px; margin-top: 8px;' }, 
        '嗅探完成后，您可以逐个页面生成测试用例。'
      ),
    ]),
    okText: '开始嗅探',
    cancelText: '取消',
    onOk: async () => {
      mcpDiscoverLoading.value = true
      try {
        console.log('开始调用 MCP 嗅探 API...')
        const result = await generateApi.mcpDiscover(projectId.value)
        console.log('MCP 嗅探结果:', result)
        message.success(result.message || `MCP 嗅探完成，发现 ${result.page_count} 个页面`)
        // 刷新页面树
        await loadPageTree()
      } catch (e: any) {
        console.error('MCP 嗅探失败:', e)
        const errorMsg = e.response?.data?.detail || e.message || 'MCP 嗅探失败'
        message.error(errorMsg)
      } finally {
        mcpDiscoverLoading.value = false
      }
    },
  })
}

async function handleGeneratePageCases(pageId: string, pagePath: string) {
  pageGenerating.value[pageId] = true
  try {
    const cases = await generateApi.mcpGeneratePageCases(pageId)
    message.success(`页面 ${pagePath} 生成 ${cases.length} 个测试用例`)
    // 刷新用例列表
    router.push({ name: 'TestCases', params: { id: projectId.value } })
    // 刷新页面树（更新用例数量）
    await loadPageTree()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '生成用例失败')
  } finally {
    pageGenerating.value[pageId] = false
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
    title: page.name + (page.is_leaf ? '' : ` (${page.case_count || 0})`),
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
</script>

<template>
  <div>
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
            
            <a-button 
              type="text" 
              size="small" 
              @click="handleRefreshTree" 
              :loading="treeLoading"
              title="刷新页面树"
            >
              <ReloadOutlined />
            </a-button>
          </a-space>
        </template>
        
        <!-- 页面树操作提示 -->
        <div style="padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 12px; color: #666;">
          💡 点击页面右侧的 + 按钮可为该页面生成测试用例
        </div>
        
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
                <a-space>
                  <a-tag size="small" color="blue">
                    {{ pageComponents[dataRef.key]?.length || 0 }} 个组件
                  </a-tag>
                  <a-button
                    v-if="dataRef.isLeaf"
                    type="text"
                    size="small"
                    @click.stop="handleGeneratePageCases(dataRef.key, dataRef.title)"
                    :loading="pageGenerating[dataRef.key]"
                    :icon="h(PlusOutlined)"
                    title="为此页面生成用例"
                    style="padding: 2px 4px; font-size: 12px;"
                  />
                </a-space>
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
        style="width: 250px; flex-shrink: 0;"
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
        <a-list 
          :data-source="associationPanel.items" 
          size="small"
          :locale="{ emptyText: '暂无关联' }"
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
  </div>
</template>
