<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  PlayCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import type { TestCase } from '../types'
import { testcaseApi, executeApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)

const cases = ref<TestCase[]>([])
const loading = ref(false)
const searchText = ref('')
const selectedIds = ref<string[]>([])
const executing = ref(false)

// New case modal
const showNewModal = ref(false)
const newForm = ref({ title: '', description: '' })
const newLoading = ref(false)

async function loadCases() {
  loading.value = true
  try {
    cases.value = await testcaseApi.list(projectId.value, {
      search: searchText.value || undefined,
    })
  } finally {
    loading.value = false
  }
}

async function handleToggle(tc: TestCase) {
  await testcaseApi.update(tc.id, { enabled: !tc.enabled })
  tc.enabled = !tc.enabled
}

async function handleDelete(id: string) {
  await testcaseApi.delete(id)
  message.success('用例已删除')
  await loadCases()
}

async function handleRunSelected() {
  const ids = selectedIds.value.length > 0
    ? selectedIds.value
    : cases.value.filter(c => c.enabled).map(c => c.id)
  if (ids.length === 0) {
    message.warning('没有可执行的用例')
    return
  }
  executing.value = true
  try {
    const execution = await executeApi.run(ids)
    message.success('执行已启动')
    router.push(`/execution/${execution.id}`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '执行失败')
  } finally {
    executing.value = false
  }
}

async function handleCreateCase() {
  if (!newForm.value.title || !newForm.value.description) {
    message.warning('请填写标题和描述')
    return
  }
  newLoading.value = true
  try {
    const tc = await testcaseApi.create({
      project_id: projectId.value,
      title: newForm.value.title,
      description: newForm.value.description,
    })
    message.success('用例已创建')
    showNewModal.value = false
    newForm.value = { title: '', description: '' }
    await loadCases()
    // Navigate to edit page to generate code
    router.push(`/testcase/${tc.id}`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    newLoading.value = false
  }
}

const rowSelection = computed(() => ({
  selectedRowKeys: selectedIds.value,
  onChange: (keys: string[]) => { selectedIds.value = keys },
}))

const columns = [
  { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, width: '35%' },
  { title: '分组', dataIndex: 'group_name', key: 'group_name', width: 100 },
  { title: '状态', key: 'enabled', width: 80, align: 'center' as const },
  { title: '操作', key: 'actions', width: 160, align: 'center' as const },
]

onMounted(loadCases)
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; margin-bottom: 16px;">
      <a-space>
        <a-input-search
          v-model:value="searchText"
          placeholder="搜索用例..."
          style="width: 250px;"
          @search="loadCases"
          allowClear
        />
      </a-space>
      <a-space>
        <a-button @click="showNewModal = true"><PlusOutlined /> 新增用例</a-button>
        <a-button type="primary" @click="handleRunSelected" :loading="executing">
          <PlayCircleOutlined />
          {{ selectedIds.length > 0 ? `执行选中 (${selectedIds.length})` : '执行全部' }}
        </a-button>
      </a-space>
    </div>

    <a-table
      :columns="columns"
      :dataSource="cases"
      :loading="loading"
      :rowSelection="rowSelection"
      rowKey="id"
      :pagination="{ pageSize: 20, showSizeChanger: true }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enabled'">
          <a-switch :checked="record.enabled" size="small" @change="handleToggle(record)" />
        </template>
        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button type="link" size="small" @click="router.push(`/testcase/${record.id}`)">
              <EditOutlined /> 编辑
            </a-button>
            <a-popconfirm title="确定删除？" @confirm="handleDelete(record.id)">
              <a-button type="link" danger size="small"><DeleteOutlined /></a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal v-model:open="showNewModal" title="新增测试用例" @ok="handleCreateCase" :confirmLoading="newLoading">
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="用例标题" required>
          <a-input v-model:value="newForm.title" placeholder="如：用户登录功能测试" />
        </a-form-item>
        <a-form-item label="自然语言描述" required>
          <a-textarea
            v-model:value="newForm.description"
            placeholder="用自然语言描述测试步骤，如：打开登录页面，输入用户名和密码，点击登录按钮，验证跳转到首页"
            :rows="4"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
