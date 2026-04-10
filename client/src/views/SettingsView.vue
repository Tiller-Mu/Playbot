<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { SaveOutlined, ApiOutlined } from '@ant-design/icons-vue'
import type { LLMSettings } from '../types'
import { settingsApi } from '../services/api'

const loading = ref(false)
const saveLoading = ref(false)
const form = ref<LLMSettings>({
  llm_endpoint: '',
  llm_api_key: '',
  llm_model: '',
})

async function loadSettings() {
  loading.value = true
  try {
    const data = await settingsApi.getLLM()
    form.value = data
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (!form.value.llm_endpoint || !form.value.llm_api_key || !form.value.llm_model) {
    message.warning('请填写完整的 LLM 配置')
    return
  }
  saveLoading.value = true
  try {
    await settingsApi.updateLLM(form.value)
    message.success('设置已保存')
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    saveLoading.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <div style="max-width: 640px;">
    <h2><ApiOutlined /> 系统设置</h2>

    <a-card title="LLM 大模型配置" style="margin-top: 16px;">
      <a-spin :spinning="loading">
        <a-form layout="vertical">
          <a-form-item label="API 端点 (Endpoint)" required>
            <a-input
              v-model:value="form.llm_endpoint"
              placeholder="https://api.openai.com/v1"
            />
            <div style="color: #999; font-size: 12px; margin-top: 4px;">
              支持 OpenAI 兼容接口，如 DeepSeek、通义千问、文心一言等
            </div>
          </a-form-item>
          <a-form-item label="API Key" required>
            <a-input-password
              v-model:value="form.llm_api_key"
              placeholder="sk-..."
            />
          </a-form-item>
          <a-form-item label="模型名称" required>
            <a-input
              v-model:value="form.llm_model"
              placeholder="gpt-4o / deepseek-chat / qwen-plus"
            />
          </a-form-item>
          <a-form-item>
            <a-button type="primary" @click="handleSave" :loading="saveLoading">
              <SaveOutlined /> 保存设置
            </a-button>
          </a-form-item>
        </a-form>
      </a-spin>
    </a-card>
  </div>
</template>
