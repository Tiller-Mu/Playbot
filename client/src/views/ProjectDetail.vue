<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  CloudDownloadOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  FileTextOutlined,
} from '@ant-design/icons-vue'
import type { Project } from '../types'
import { projectApi, generateApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)
const project = ref<Project | null>(null)
const loading = ref(false)
const cloneLoading = ref(false)
const generateLoading = ref(false)

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

async function handleClone() {
  cloneLoading.value = true
  try {
    const res = await projectApi.clone(projectId.value)
    message.success(res.message)
    await loadProject()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '代码拉取失败')
  } finally {
    cloneLoading.value = false
  }
}

async function handleGenerate() {
  generateLoading.value = true
  try {
    const cases = await generateApi.generate(projectId.value)
    message.success(`成功生成 ${cases.length} 条测试用例`)
    // Refresh child view
    router.replace({ name: 'TestCases', params: { id: projectId.value } })
  } catch (e: any) {
    message.error(e.response?.data?.detail || '用例生成失败')
  } finally {
    generateLoading.value = false
  }
}

function switchTab(key: string) {
  if (key === 'executions') {
    router.push(`/project/${projectId.value}/executions`)
  } else {
    router.push(`/project/${projectId.value}`)
  }
}

onMounted(loadProject)
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
        <a-button
          type="primary"
          @click="handleGenerate"
          :loading="generateLoading"
          :disabled="!project?.repo_path"
        >
          <ThunderboltOutlined /> 自动生成用例
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

    <a-tabs :activeKey="activeTab" @change="switchTab" style="margin-top: 8px;">
      <a-tab-pane key="cases">
        <template #tab><FileTextOutlined /> 测试用例</template>
      </a-tab-pane>
      <a-tab-pane key="executions">
        <template #tab><HistoryOutlined /> 执行历史</template>
      </a-tab-pane>
    </a-tabs>

    <router-view :key="route.fullPath" />
  </div>
</template>
