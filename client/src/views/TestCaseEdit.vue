<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  SendOutlined,
  CodeOutlined,
  FileTextOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'
import type { TestCase } from '../types'
import { testcaseApi } from '../services/api'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => route.params.id as string)

const testCase = ref<TestCase | null>(null)
const loading = ref(false)
const editLoading = ref(false)
const saveLoading = ref(false)
const showCode = ref(false)
const nlInstruction = ref('')

async function loadCase() {
  loading.value = true
  try {
    testCase.value = await testcaseApi.get(caseId.value)
  } finally {
    loading.value = false
  }
}

async function handleNLEdit() {
  if (!nlInstruction.value.trim()) {
    message.warning('请输入修改指令')
    return
  }
  editLoading.value = true
  try {
    const result = await testcaseApi.nlEdit(caseId.value, nlInstruction.value)
    if (testCase.value) {
      testCase.value.description = result.description
      testCase.value.script_content = result.script_content
    }
    message.success('用例已更新')
    nlInstruction.value = ''
    showCode.value = true // 展开代码让用户确认
  } catch (e: any) {
    message.error(e.response?.data?.detail || '修改失败')
  } finally {
    editLoading.value = false
  }
}

async function handleSave() {
  if (!testCase.value) return
  saveLoading.value = true
  try {
    await testcaseApi.update(caseId.value, {
      title: testCase.value.title,
      description: testCase.value.description,
      script_content: testCase.value.script_content,
    })
    message.success('已保存')
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    saveLoading.value = false
  }
}

onMounted(loadCase)
</script>

<template>
  <div style="max-width: 960px; margin: 0 auto;">
    <a-page-header
      :title="testCase?.title || '加载中...'"
      @back="router.back()"
    >
      <template #extra>
        <a-button @click="showCode = !showCode">
          <CodeOutlined /> {{ showCode ? '隐藏代码' : '查看代码' }}
        </a-button>
        <a-button type="primary" @click="handleSave" :loading="saveLoading">
          <SaveOutlined /> 保存
        </a-button>
      </template>
    </a-page-header>

    <a-spin :spinning="loading">
      <a-card v-if="testCase" style="margin-bottom: 16px;">
        <template #title><FileTextOutlined /> 自然语言描述</template>
        <a-textarea
          v-model:value="testCase.description"
          :rows="6"
          style="font-size: 15px; line-height: 1.8;"
        />
      </a-card>

      <a-card v-if="testCase && showCode" style="margin-bottom: 16px;">
        <template #title><CodeOutlined /> 测试脚本代码</template>
        <a-textarea
          v-model:value="testCase.script_content"
          :rows="20"
          style="font-family: 'Courier New', Consolas, monospace; font-size: 13px; line-height: 1.6;"
        />
      </a-card>

      <a-card title="自然语言修改" v-if="testCase">
        <div style="display: flex; gap: 8px;">
          <a-input
            v-model:value="nlInstruction"
            placeholder="用自然语言描述你要做的修改，如：'在登录后增加一步验证用户头像是否显示'"
            @pressEnter="handleNLEdit"
            style="flex: 1;"
            size="large"
          />
          <a-button
            type="primary"
            size="large"
            @click="handleNLEdit"
            :loading="editLoading"
          >
            <SendOutlined /> 应用修改
          </a-button>
        </div>
        <p style="color: #999; margin-top: 8px; font-size: 12px;">
          LLM 会根据你的指令修改自然语言描述和对应的测试代码，修改后请检查确认。
        </p>
      </a-card>
    </a-spin>
  </div>
</template>
