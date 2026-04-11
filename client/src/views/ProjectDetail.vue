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
  FolderOutlined,
  FileOutlined,
} from '@ant-design/icons-vue'
import type { Project, TestPage } from '../types'
import { projectApi, pageApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)
const project = ref<Project | null>(null)
const loading = ref(false)
const cloneLoading = ref(false)
const generateLoading = ref(false)
const treeLoading = ref(false)

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
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载页面树失败')
  } finally {
    treeLoading.value = false
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
function convertToTreeData(pages: TestPage[]) {
  return pages.map(page => ({
    key: page.id,
    title: page.name + (page.is_leaf ? '' : ` (${page.case_count || 0})`),
    icon: page.is_leaf ? FileOutlined : FolderOutlined,
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
        <a-button @click="handleClone" :loading="cloneLoading">
          <CloudDownloadOutlined /> {{ project?.repo_path ? '重新拉取' : '拉取代码' }}
        </a-button>
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
      <!-- 左侧页面树 -->
      <a-card 
        title="页面树" 
        :bordered="true" 
        style="width: 300px; flex-shrink: 0;"
        :bodyStyle="{ padding: '12px' }"
      >
        <template #extra>
          <a-space>
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
        
        <div v-if="!project?.repo_path" style="padding: 20px; text-align: center; color: #999;">
          请先拉取代码
        </div>
        
        <a-tree
          v-else
          :tree-data="convertToTreeData(pageTree)"
          :expanded-keys="treeExpandedKeys"
          @expand="(keys) => treeExpandedKeys = keys as string[]"
          @select="(keys, { node }) => handlePageSelect(keys[0] as string, (node as any).dataRef)"
          :selected-keys="selectedPageId ? [selectedPageId] : []"
          :show-line="true"
        >
          <template #title="{ title }">
            <span>{{ title }}</span>
          </template>
        </a-tree>
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
