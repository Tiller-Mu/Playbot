<template>
  <a-modal
    :open="props.open"
    title="📹 页面探索录制"
    :width="700"
    :footer="null"
    :maskClosable="false"
    :closable="true"
    @cancel="handleCancel"
  >
    <!-- 状态显示 -->
    <a-statistic
      :title="statusText"
      :value="durationText"
      :value-style="{ color: statusColor }"
      style="text-align: center; margin-bottom: 20px"
    >
      <template #prefix>
        <component :is="statusIcon" />
      </template>
    </a-statistic>
    
    <!-- 控制按钮 -->
    <a-space size="large" style="display: flex; justify-content: center; margin-bottom: 20px">
      <a-button 
        type="primary" 
        @click="handleStartOrResume" 
        :disabled="status === 'recording'"
        :loading="startLoading"
      >
        <template #icon><PlayCircleOutlined /></template>
        {{ status === 'paused' ? '继续录制' : '开始录制' }}
      </a-button>
      
      <a-button 
        @click="handlePause" 
        :disabled="status !== 'recording'"
      >
        <template #icon><PauseCircleOutlined /></template>
        暂停录制
      </a-button>
      
      <a-button 
        danger 
        @click="handleStop" 
        :disabled="status === 'idle' || status === 'completed'"
      >
        <template #icon><StopOutlined /></template>
        完成录制
      </a-button>
    </a-space>
    
    <!-- 实时统计 -->
    <a-descriptions bordered size="small" :column="2">
      <a-descriptions-item label="已记录动作">
        <a-tag color="blue">{{ actionCount }}</a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="录制状态">
        <a-badge :status="statusBadge" :text="statusText" />
      </a-descriptions-item>
      <a-descriptions-item label="最后捕获" :span="2">
        <span v-if="lastCapturedUrl" style="color: #52c41a">
          ✅ {{ lastCapturedUrl }}
        </span>
        <span v-else style="color: #999">
          等待页面访问...
        </span>
      </a-descriptions-item>
    </a-descriptions>
    
    <!-- 页面列表 -->
    <div v-if="recordedActions.length > 0" style="margin-top: 16px">
      <h4 style="margin-bottom: 8px">生成的测试动作：</h4>
      <a-list
        :data-source="recordedActions"
        :pagination="{ pageSize: 5 }"
        size="small"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta :title="item.statement || '未知动作'">
              <template #description>
                <code>{{ item.raw_data?.action }}</code> on {{ item.raw_data?.tag }}
              </template>
            </a-list-item-meta>
          </a-list-item>
        </template>
      </a-list>
    </div>
    
    <!-- 操作提示 -->
    <a-alert 
      :type="status === 'recording' ? 'success' : 'info'" 
      show-icon 
      style="margin-top: 16px"
    >
      <template #message>
        <div v-if="status === 'recording'">
          <p style="margin: 0 0 8px 0; color: #52c41a; font-weight: bold">
            🎬 正在录制中...
          </p>
          <p style="margin: 0; color: #666">
            请在<strong>新打开的浏览器窗口</strong>中访问页面<br>
            系统会自动记录您访问的所有页面
          </p>
        </div>
        <div v-else>
          <p style="margin: 0 0 8px 0">💡 录制提示：</p>
          <ul style="margin: 0; padding-left: 20px">
            <li>点击"开始录制"后，<strong>系统会自动打开一个新的浏览器窗口</strong></li>
            <li>在这个窗口中正常访问网站页面即可</li>
            <li>系统会自动记录您访问的所有页面，<strong>不会影响您原有的浏览器</strong></li>
            <li>随时可以暂停，后续继续录制</li>
            <li>重复访问的页面只记录一次（自动去重）</li>
            <li>完成录制后，浏览器窗口会自动关闭，并生成覆盖率报告</li>
          </ul>
        </div>
      </template>
    </a-alert>
    
    <!-- 关闭按钮 -->
    <div style="text-align: right; margin-top: 16px">
      <a-button @click="handleCancel">
        关闭窗口
      </a-button>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { 
  PlayCircleOutlined, 
  PauseCircleOutlined, 
  StopOutlined,
  ClockCircleOutlined,
  VideoCameraOutlined,
  PauseCircleFilled,
  CheckCircleOutlined
} from '@ant-design/icons-vue'
import { recordingApi } from '../services/api'
import { message, Modal } from 'ant-design-vue'

const props = defineProps<{
  open: boolean
  projectId: string | undefined
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'recording-complete': [report: any]
}>()

const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

const status = ref<'idle' | 'recording' | 'paused' | 'completed'>('idle')
const startLoading = ref(false)
const recordedActions = ref<any[]>([])
const duration = ref(0)
const lastCapturedUrl = ref<string>('')  // 最后捕获的URL
let localTimer: number | null = null  // 本地计时器

// 状态文本
const statusText = computed(() => {
  const map: Record<string, string> = {
    idle: '准备就绪',
    recording: '正在录制',
    paused: '已暂停',
    completed: '录制完成'
  }
  return map[status.value]
})

// 状态颜色
const statusColor = computed(() => {
  const map: Record<string, string> = {
    idle: '#999',
    recording: '#52c41a',
    paused: '#faad14',
    completed: '#1890ff'
  }
  return map[status.value]
})

// 状态图标
const statusIcon = computed(() => {
  const map: Record<string, any> = {
    idle: ClockCircleOutlined,
    recording: VideoCameraOutlined,
    paused: PauseCircleFilled,
    completed: CheckCircleOutlined
  }
  return map[status.value]
})

// 状态徽标
const statusBadge = computed(() => {
  const map: Record<string, 'default' | 'processing' | 'warning' | 'success'> = {
    idle: 'default',
    recording: 'processing',
    paused: 'warning',
    completed: 'success'
  }
  return map[status.value]
})

// 时长文本
const durationText = computed(() => {
  const totalSeconds = Math.floor(duration.value)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
})

const actionCount = computed(() => recordedActions.value.length)

// 轮询获取状态
let pollingTimer: number | null = null

// 监听弹窗打开
watch(() => props.open, async (newVal) => {
  if (newVal) {
    // 先验证项目存在
    if (!props.projectId) {
      message.error('项目ID不存在')
      visible.value = false
      return
    }
    
    await loadStatus()
    
    // 如果是已完成或初始状态，重置本地显示，准备开始新录制
    if (status.value === 'completed' || status.value === 'idle') {
      recordedActions.value = []
      duration.value = 0
      lastCapturedUrl.value = ''
    }
    
    // 每2秒轮询一次
    pollingTimer = window.setInterval(loadStatus, 2000)
    // 启动本地计时器
    localTimer = window.setInterval(() => {
      if (status.value === 'recording') {
        duration.value += 1
      }
    }, 1000)
  } else {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
    if (localTimer) {
      clearInterval(localTimer)
      localTimer = null
    }
  }
})

// 组件卸载时清理
onUnmounted(() => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
  }
  if (localTimer) {
    clearInterval(localTimer)
  }
})

// 加载状态
async function loadStatus() {
  if (!props.projectId) return
  
  try {
    const res = await recordingApi.getStatus(props.projectId)
    const oldStatus = status.value
    status.value = res.status as any
    
    // 只有在正在录制、已暂停，或者刚刚在当前会话点击了停止时，才同步数据
    const isActive = status.value === 'recording' || status.value === 'paused'
    const isJustFinished = oldStatus === 'recording' && status.value === 'completed'
    
    // 如果碰到了意外退出的打断状态，自动触发打扫数据的收尾工作
    if (res.status === 'interrupted') {
      message.warning('检测到录制浏览器可能被强行关闭，系统正为您自动打包录制数据...')
      await handleStop()
      return
    }
    
    if (isActive || isJustFinished) {
      // 优化时长同步：只有当后端时间显著大于前端（误差>5秒），或者状态刚切换时才覆盖
      const backendDuration = Math.floor(res.duration || 0)
      if (Math.abs(backendDuration - duration.value) > 5 || oldStatus !== status.value) {
        duration.value = backendDuration
      }
      
      // 转换动作历史列表
      if (res.actions && res.actions.length > 0) {
        recordedActions.value = res.actions;
        // 显示最后捕获的页面
        lastCapturedUrl.value = res.actions[res.actions.length - 1]?.url || '';
      }
    } else if (status.value === 'completed' || status.value === 'idle') {
      // 如果是刚打开弹窗看到的完成状态，说明是旧数据，清空显示
      if (oldStatus === 'idle' || !isActive) {
        recordedActions.value = []
        duration.value = 0
        lastCapturedUrl.value = ''
      }
    }
  } catch (e: any) {
    console.error('获取录制状态失败', e)
  }
}

// 开始/继续录制
async function handleStartOrResume() {
  if (!props.projectId) {
    message.error('项目ID不存在')
    return
  }
  
  startLoading.value = true
  try {
    const res = await recordingApi.start(props.projectId)
    status.value = res.status as any
    message.success(res.message)
  } catch (e: any) {
    // 如果是404错误，显示更友好的提示
    if (e.response?.status === 404) {
      message.error('项目不存在，无法开始录制。请检查项目是否已删除。')
    } else {
      message.error(e.response?.data?.detail || '启动录制失败')
    }
  } finally {
    startLoading.value = false
  }
}

// 暂停录制
async function handlePause() {
  if (!props.projectId) return
  
  try {
    const res = await recordingApi.pause(props.projectId)
    status.value = res.status as any
    message.info(res.message)
  } catch (e: any) {
    message.error(e.message || '暂停录制失败')
  }
}

// 停止录制
async function handleStop() {
  if (!props.projectId) return
  
  try {
    const res = await recordingApi.stop(props.projectId)
    status.value = res.status as any
    message.success(res.message || '录制已停止，数据已同步到页面树')
    
    // 触发完成事件，传递覆盖率报告
    emit('recording-complete', res.report)
    
    // 自动关闭弹窗
    setTimeout(() => {
      visible.value = false
    }, 1500)
  } catch (e: any) {
    message.error(e.response?.data?.detail || e.message || '停止录制失败')
  }
}

// 取消
function handleCancel() {
  if (status.value === 'recording' || status.value === 'paused') {
    Modal.confirm({
      title: '⚠️ 录制仍在进行中',
      content: '关闭本控制台将自动终止录制进程。是否立即结束并生成报告？',
      okText: '停止并生成报告',
      cancelText: '继续录制 (不关闭)',
      maskClosable: true,
      onOk: async () => {
        await handleStop()
      },
      onCancel: () => {
        // 用户取消，什么都不做，弹窗保持打开状态
      }
    })
  } else {
    // 如果是已完成状态，也触发一次完成事件以刷新列表
    if (status.value === 'completed') {
      emit('recording-complete', null)
    }
    emit('update:open', false)
  }
}

// 格式化时间
function formatTime(timestamp: number | null): string {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
/* 可选：自定义样式 */
</style>
