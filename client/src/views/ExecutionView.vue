<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  MinusCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons-vue'
import type { Execution, ExecutionDetail } from '../types'
import { executeApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const executionId = computed(() => route.params.id as string)

const execution = ref<Execution | null>(null)
const details = ref<ExecutionDetail[]>([])
const loading = ref(false)
let pollTimer: number | null = null
let ws: WebSocket | null = null

async function loadExecution() {
  loading.value = true
  try {
    execution.value = await executeApi.get(executionId.value)
    details.value = await executeApi.details(executionId.value)
  } finally {
    loading.value = false
  }
}

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${location.host}/ws/execution/${executionId.value}`)
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'execution:progress') {
      // Reload details
      executeApi.details(executionId.value).then(d => details.value = d)
    }
    if (data.type === 'execution:complete') {
      loadExecution()
    }
  }
  ws.onerror = () => {
    // Fallback to polling
    startPolling()
  }
}

function startPolling() {
  pollTimer = window.setInterval(async () => {
    await loadExecution()
    if (execution.value && !['pending', 'running'].includes(execution.value.status)) {
      if (pollTimer) clearInterval(pollTimer)
    }
  }, 3000)
}

const statusColor = (s: string) => {
  const map: Record<string, string> = {
    passed: '#52c41a', failed: '#ff4d4f', running: '#1890ff',
    pending: '#faad14', error: '#ff4d4f', skipped: '#d9d9d9',
  }
  return map[s] || '#999'
}

const progressPercent = computed(() => {
  if (!execution.value || !execution.value.total_cases) return 0
  return Math.round(
    ((execution.value.passed_count + execution.value.failed_count + execution.value.skipped_count)
    / execution.value.total_cases) * 100
  )
})

const columns = [
  { title: '用例 ID', dataIndex: 'test_case_id', key: 'test_case_id', ellipsis: true, width: 280 },
  { title: '状态', key: 'status', width: 100, align: 'center' as const },
  { title: '耗时', key: 'duration', width: 100, align: 'center' as const },
  { title: '错误信息', dataIndex: 'error_message', key: 'error', ellipsis: true },
]

onMounted(() => {
  loadExecution()
  connectWs()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (ws) ws.close()
})
</script>

<template>
  <div>
    <a-page-header
      title="执行详情"
      @back="router.back()"
    >
      <template #extra>
        <a-tag v-if="execution" :color="statusColor(execution.status)" style="font-size: 14px; padding: 4px 12px;">
          {{ execution.status.toUpperCase() }}
        </a-tag>
      </template>

      <a-row :gutter="16" v-if="execution">
        <a-col :span="6">
          <a-statistic title="总用例数" :value="execution.total_cases" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="通过" :value="execution.passed_count" :value-style="{ color: '#52c41a' }" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="失败" :value="execution.failed_count" :value-style="{ color: '#ff4d4f' }" />
        </a-col>
        <a-col :span="6">
          <a-progress type="circle" :percent="progressPercent" :size="80" />
        </a-col>
      </a-row>
    </a-page-header>

    <a-table
      :columns="columns"
      :dataSource="details"
      :loading="loading"
      rowKey="id"
      style="margin-top: 16px;"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="statusColor(record.status)">
            <CheckCircleOutlined v-if="record.status === 'passed'" />
            <CloseCircleOutlined v-if="record.status === 'failed'" />
            <LoadingOutlined v-if="record.status === 'running'" />
            <ClockCircleOutlined v-if="record.status === 'pending'" />
            <MinusCircleOutlined v-if="record.status === 'skipped'" />
            {{ record.status }}
          </a-tag>
        </template>
        <template v-if="column.key === 'duration'">
          {{ record.duration_ms ? (record.duration_ms / 1000).toFixed(1) + 's' : '-' }}
        </template>
      </template>
    </a-table>
  </div>
</template>
