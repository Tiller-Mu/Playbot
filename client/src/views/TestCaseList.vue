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

// AI用例规划结果
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


// AI用例规划（LangGraph）
async function handleAgentGenerate() {
  if (selectedPageIds.value.length === 0) {
    message.warning('请先在左侧勾选一个或多个页面')
    return
  }
  
  if (selectedPageIds.value.length > 1) {
    message.info('AI用例规划暂只支持单页面，将使用第一个选中的页面')
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
    
    message.success(`AI用例规划完成！共 ${result.generated_count} 个用例`)
    await loadCases()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'AI用例规划失败')
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

const compiling = ref(false)
async function handleCompileSelected() {
  const ids = selectedIds.value.length > 0
    ? selectedIds.value
    : cases.value.filter(c => c.enabled).map(c => c.id)
  if (ids.length === 0) {
    message.warning('请选择要编译的用例')
    return
  }
  
  emit('clear-mcp-log')
  emit('open-mcp-log')
  emit('set-mcp-running', true)
  
  compiling.value = true
  // 串行单线程执行，防止被大模型限流
  try {
    let successCount = 0
    message.loading({ content: `正在依次生成 ${ids.length} 个用例...`, key: 'compile_progress', duration: 0 })
    
    for (const [index, id] of ids.entries()) {
      message.loading({ content: `生成中 (${index + 1}/${ids.length})...`, key: 'compile_progress', duration: 0 })
      await testcaseApi.compile(id)
      successCount++
    }
    
    message.success({ content: `已成功生成 ${successCount} 个经过审查优化的用例！`, key: 'compile_progress', duration: 3 })
    await loadCases()
  } catch (e: any) {
    message.error({ content: `生成中断: ${e.response?.data?.detail || '未知错误'}`, key: 'compile_progress', duration: 5 })
  } finally {
    compiling.value = false
    emit('set-mcp-running', false)
  }
}

const healing = ref(false)
async function handleHealSelected() {
  const ids = selectedIds.value
  if (ids.length === 0) {
    message.warning('请选择需要自愈的失败用例')
    return
  }
  
  // 检查是否都包含错误信息
  const failedCases = cases.value.filter(c => ids.includes(c.id) && ['failed', 'error'].includes(c.latest_status) && c.latest_error_message)
  if (failedCases.length === 0) {
    message.warning('选中的用例没有最近的执行报错日志，无法自愈')
    return
  }

  emit('clear-mcp-log')
  emit('open-mcp-log')
  emit('set-mcp-running', true)
  
  healing.value = true
  try {
    let successCount = 0
    message.loading({ content: `正在依次诊断修复 ${failedCases.length} 个失败脚本...`, key: 'heal_progress', duration: 0 })
    
    for (const [index, tc] of failedCases.entries()) {
      message.loading({ content: `诊断中 (${index + 1}/${failedCases.length})...`, key: 'heal_progress', duration: 0 })
      await testcaseApi.heal(tc.id, tc.latest_error_message!)
      successCount++
    }
    
    message.success({ content: `已成功自愈修复 ${successCount} 个脚本！`, key: 'heal_progress', duration: 3 })
    await loadCases()
  } catch (e: any) {
    message.error({ content: `自愈中断: ${e.response?.data?.detail || '未知错误'}`, key: 'heal_progress', duration: 5 })
  } finally {
    healing.value = false
    emit('set-mcp-running', false)
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
  { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, width: '25%' },
  { title: '分组', dataIndex: 'group_name', key: 'group_name', width: 80 },
  { title: '代码状态', key: 'code_status', width: 90, align: 'center' as const },
  { title: '最近执行', key: 'exec_status', width: 100, align: 'center' as const },
  { title: '启用', key: 'enabled', width: 60, align: 'center' as const },
  { title: '操作', key: 'actions', width: 140, align: 'center' as const },
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
          {{ selectedPageIds.length > 0 ? `🤖 AI用例规划 (${selectedPageIds.length})` : '🤖 AI用例规划' }}
        </a-button>
        <a-button 
          type="primary" 
          @click="handleCompileSelected" 
          :loading="compiling"
          style="background-color: #52c41a; border-color: #52c41a;"
        >
          ⚡ {{ selectedIds.length > 0 ? `AI用例生成 (${selectedIds.length})` : '生成全部用例' }}
        </a-button>
        <a-button 
          type="primary" 
          @click="handleHealSelected" 
          :loading="healing"
          style="background-color: #faad14; border-color: #faad14;"
          :disabled="selectedIds.length === 0"
        >
          🏥 一键 AI 自愈 ({{ selectedIds.length }})
        </a-button>
        <a-button type="primary" @click="showNewModal = true"><PlusOutlined /> 新增用例</a-button>
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
        <template v-if="column.key === 'code_status'">
          <a-tag v-if="record.is_compiled" color="success">已生成</a-tag>
          <a-tag v-else color="default">待生成</a-tag>
        </template>
        <template v-if="column.key === 'exec_status'">
          <template v-if="record.latest_status">
            <a-popover v-if="record.latest_status === 'failed' || record.latest_status === 'error'" title="报错详情">
              <template #content>
                <div style="max-width: 500px; max-height: 300px; overflow: auto; white-space: pre-wrap;">
                  {{ record.latest_error_message }}
                </div>
              </template>
              <a-tag color="error" style="cursor: pointer;">失败 (悬停查看)</a-tag>
            </a-popover>
            <a-tag v-else-if="record.latest_status === 'passed'" color="success">通过</a-tag>
            <a-tag v-else color="default">{{ record.latest_status }}</a-tag>
          </template>
          <span v-else style="color: #999;">-</span>
        </template>
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
