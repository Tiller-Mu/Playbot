<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  PlayCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  ThunderboltOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'
import type { TestCase } from '../types'
import { testcaseApi, executeApi, pageApi } from '../services/api'

const emit = defineEmits(['open-mcp-log', 'clear-mcp-log', 'set-mcp-running'])
const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)
const pageId = computed(() => route.query.page_id as string | undefined)

const cases = ref<TestCase[]>([])
const loading = ref(false)
const searchText = ref('')
const selectedIds = ref<string[]>([])
const executing = ref(false)
const agentGenerating = ref(false)  // 智能体生成状态
const selectedPageIds = ref<string[]>([])  // 从ProjectDetail传入的选中页面

// 智能体生成结果
const showAgentResult = ref(false)
const agentResult = ref<{
  page_path: string;
  generated_count: number;
  test_cases: TestCase[];
  analysis: {
    code: string;
    dom: string;
    strategy: string;
  };
  logs: { level: string; message: string; time: string }[];
} | null>(null)
const activeAgentTab = ref('cases')  // cases | analysis | logs

// New case modal
const showNewModal = ref(false)
const newForm = ref({ title: '', description: '' })
const newLoading = ref(false)

async function loadCases() {
  loading.value = true
  try {
    // 如果有 page_id，只加载该页面的用例
    const params: any = {
      search: searchText.value || undefined,
    }
    
    if (pageId.value) {
      // 使用页面 API 获取该页面的用例
      cases.value = await pageApi.getCases(pageId.value)
      // 前端过滤搜索结果
      if (searchText.value) {
        cases.value = cases.value.filter(c => 
          c.title.includes(searchText.value) || 
          c.description.includes(searchText.value)
        )
      }
    } else {
      // 否则使用项目 API 获取所有用例
      cases.value = await testcaseApi.list(projectId.value, params)
    }
  } finally {
    loading.value = false
  }
}


// 智能体生成用例（LangGraph）
async function handleAgentGenerate() {
  if (selectedPageIds.value.length === 0) {
    message.warning('请先在左侧勾选一个或多个页面')
    return
  }
  
  if (selectedPageIds.value.length > 1) {
    message.info('智能体生成暂只支持单页面，将使用第一个选中的页面')
  }
  
  agentGenerating.value = true
  emit('clear-mcp-log')
  emit('open-mcp-log')
  emit('set-mcp-running', true)
  
  try {
    const pid = selectedPageIds.value[0]
    const result = await pageApi.generateWithAgent(pid)
    
    agentResult.value = result
    showAgentResult.value = true
    
    message.success(`智能体生成完成！共 ${result.generated_count} 个用例`)
    await loadCases()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '智能体生成失败')
  } finally {
    agentGenerating.value = false
    emit('set-mcp-running', false)
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

async function handleRunSelected(headless: boolean = true) {
  const ids = selectedIds.value.length > 0
    ? selectedIds.value
    : cases.value.filter(c => c.enabled).map(c => c.id)
  if (ids.length === 0) {
    message.warning('没有可执行的用例')
    return
  }
  executing.value = true
  try {
    const execution = await executeApi.run(ids, headless)
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

// 监听 page_id 变化，重新加载用例
watch(() => route.query.page_id, () => {
  loadCases()
})

// 监听 page_ids 变化（复选的多个页面）
watch(
  () => route.query.page_ids,
  (newPageIds) => {
    if (newPageIds) {
      selectedPageIds.value = (newPageIds as string).split(',')
    } else {
      selectedPageIds.value = []
    }
  },
  { immediate: true }
)

// 初始化：从路由中恢复选中状态
onMounted(() => {
  if (route.query.page_ids) {
    selectedPageIds.value = (route.query.page_ids as string).split(',')
  }
})

onMounted(loadCases)
</script>

<template>
  <div>
    <!-- 当前选中的页面提示 -->
    <a-alert 
      v-if="pageId" 
      :message="`当前页面: ${$route.query.page_path || '加载中...'}`" 
      type="info" 
      show-icon 
      closable
      style="margin-bottom: 16px;"
    />
    
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
        <a-button 
          type="primary" 
          @click="handleAgentGenerate" 
          :loading="agentGenerating"
          :disabled="selectedPageIds.length === 0"
          danger
        >
          <RobotOutlined /> 
          {{ selectedPageIds.length > 0 ? `🤖 智能体生成 (${selectedPageIds.length})` : '🤖 智能体生成' }}
        </a-button>
        <a-button @click="showNewModal = true"><PlusOutlined /> 新增用例</a-button>
        <a-dropdown placement="bottomRight">
          <a-button type="primary" :loading="executing">
            <PlayCircleOutlined />
            {{ selectedIds.length > 0 ? `执行选中 (${selectedIds.length})` : '执行全部' }}
          </a-button>
          <template #overlay>
            <a-menu>
              <a-menu-item key="headed" @click="handleRunSelected(false)">
                <PlayCircleOutlined style="margin-right: 8px;" />有头执行 (显示浏览器)
              </a-menu-item>
              <a-menu-item key="headless" @click="handleRunSelected(true)">
                <ThunderboltOutlined style="margin-right: 8px;" />极速倒计时执行 (无痕)
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
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
        <a-form-item v-if="pageId" label="关联页面">
          <a-tag color="blue">当前选中的页面</a-tag>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 智能体生成结果弹窗 -->
    <a-modal
      v-model:open="showAgentResult"
      title="🤖 智能体生成结果"
      width="900px"
      :footer="null"
    >
      <div v-if="agentResult">
        <a-alert
          :message="`页面: ${agentResult.page_path} | 生成用例: ${agentResult.generated_count} 个`"
          type="success"
          show-icon
          style="margin-bottom: 16px;"
        />
        
        <a-tabs v-model:activeKey="activeAgentTab">
          <!-- 生成的用例 -->
          <a-tab-pane key="cases" tab="生成的用例">
            <a-list :data-source="agentResult.test_cases" bordered>
              <template #renderItem="{ item, index }">
                <a-list-item>
                  <a-list-item-meta
                    :title="`${index + 1}. ${item.title}`"
                    :description="item.description"
                  />
                  <a-button 
                    type="link" 
                    size="small"
                    @click="router.push(`/testcase/${item.id}`)"
                  >
                    查看代码
                  </a-button>
                </a-list-item>
              </template>
            </a-list>
          </a-tab-pane>
          
          <!-- 分析过程 -->
          <a-tab-pane key="analysis" tab="分析过程">
            <a-collapse>
              <a-collapse-panel key="strategy" header="测试策略">
                <pre style="white-space: pre-wrap; font-size: 12px;">{{ agentResult.analysis.strategy }}</pre>
              </a-collapse-panel>
              <a-collapse-panel key="code" header="代码分析">
                <pre style="white-space: pre-wrap; font-size: 12px;">{{ agentResult.analysis.code }}</pre>
              </a-collapse-panel>
              <a-collapse-panel key="dom" header="DOM分析">
                <pre style="white-space: pre-wrap; font-size: 12px;">{{ agentResult.analysis.dom }}</pre>
              </a-collapse-panel>
            </a-collapse>
          </a-tab-pane>
        </a-tabs>
      </div>
    </a-modal>
  </div>
</template>
