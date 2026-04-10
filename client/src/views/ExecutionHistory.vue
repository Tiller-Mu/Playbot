<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {} from '@ant-design/icons-vue'
import type { Execution } from '../types'
import { executeApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)

const executions = ref<Execution[]>([])
const loading = ref(false)

async function loadHistory() {
  loading.value = true
  try {
    executions.value = await executeApi.history(projectId.value)
  } finally {
    loading.value = false
  }
}

const statusColor = (s: string) => {
  const map: Record<string, string> = {
    passed: 'green', failed: 'red', running: 'blue', pending: 'orange', error: 'red',
  }
  return map[s] || 'default'
}

const columns = [
  { title: '时间', key: 'time', width: 180 },
  { title: '状态', key: 'status', width: 100, align: 'center' as const },
  { title: '总数', dataIndex: 'total_cases', key: 'total', width: 80, align: 'center' as const },
  { title: '通过', dataIndex: 'passed_count', key: 'passed', width: 80, align: 'center' as const },
  { title: '失败', dataIndex: 'failed_count', key: 'failed', width: 80, align: 'center' as const },
  { title: '操作', key: 'actions', width: 100, align: 'center' as const },
]

onMounted(loadHistory)
</script>

<template>
  <a-table
    :columns="columns"
    :dataSource="executions"
    :loading="loading"
    rowKey="id"
  >
    <template #bodyCell="{ column, record }">
      <template v-if="column.key === 'time'">
        {{ record.start_time ? new Date(record.start_time).toLocaleString() : new Date(record.created_at).toLocaleString() }}
      </template>
      <template v-if="column.key === 'status'">
        <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
      </template>
      <template v-if="column.key === 'actions'">
        <a-button type="link" size="small" @click="router.push(`/execution/${record.id}`)">
          查看详情
        </a-button>
      </template>
    </template>
  </a-table>
</template>
