<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { SaveOutlined, ApiOutlined } from '@ant-design/icons-vue'
import type { LLMSettings } from '../types'
import { settingsApi } from '../services/api'

// 模型厂商配置
const modelProviders = [
  {
    label: 'OpenAI',
    value: 'openai',
    endpoint: 'https://api.openai.com/v1',
    models: ['gpt-5.1', 'gpt-5.1-mini', 'gpt-5.1-nano', 'gpt-5.1-thinking', 'gpt-5', 'o3', 'o4-mini'],
  },
  {
    label: '阿里通义千问',
    value: 'dashscope',
    endpoint: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: ['qwen3.6-plus', 'qwen3.5-flash', 'qwen3-max', 'qwen3-plus', 'qwen3-turbo'],
  },
  {
    label: '智谱 AI',
    value: 'zhipu',
    endpoint: 'https://open.bigmodel.cn/api/paas/v4',
    models: ['glm-5.1', 'glm-5', 'glm-5-turbo', 'glm-5v-turbo', 'glm-4.7', 'glm-4.7-flash', 'glm-4.6'],
  },
  {
    label: 'MiniMax',
    value: 'minimax',
    endpoint: 'https://api.minimax.chat/v1',
    models: ['MiniMax-M2.7', 'MiniMax-M2.1', 'MiniMax-M1', 'Hailuo-02'],
  },
  {
    label: '小米大模型',
    value: 'xiaomi',
    endpoint: 'https://api.xiaoai.mi.com/v1',
    models: ['MiMo-V2-Pro', 'MiMo-V2-Omni', 'MiMo-V2-Flash'],
  },
  {
    label: 'DeepSeek',
    value: 'deepseek',
    endpoint: 'https://api.deepseek.com/v1',
    models: ['deepseek-chat', 'deepseek-reasoner', 'deepseek-coder'],
  },
]

const loading = ref(false)
const saveLoading = ref(false)
const selectedProvider = ref<string>('')
const selectedModel = ref<string>('')

const form = ref<LLMSettings>({
  llm_endpoint: '',
  llm_api_key: '',
  llm_model: '',
})

// 当前厂商的模型列表
const currentModels = ref<string[]>([])

// 监听厂商选择变化
watch(selectedProvider, (providerValue) => {
  const provider = modelProviders.find(p => p.value === providerValue)
  if (provider) {
    form.value.llm_endpoint = provider.endpoint
    currentModels.value = provider.models
    // 自动选择第一个模型
    if (provider.models.length > 0) {
      selectedModel.value = provider.models[0]
      form.value.llm_model = provider.models[0]
    }
  }
})

// 监听模型选择变化
watch(selectedModel, (modelValue) => {
  if (modelValue) {
    form.value.llm_model = modelValue
  }
})

async function loadSettings() {
  loading.value = true
  try {
    const data = await settingsApi.getLLM()
    form.value = data
    
    // 根据已保存的端点自动识别厂商
    const matchedProvider = modelProviders.find(p => p.endpoint === data.llm_endpoint)
    if (matchedProvider) {
      selectedProvider.value = matchedProvider.value
      currentModels.value = matchedProvider.models
      selectedModel.value = data.llm_model
    }
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
          <a-form-item label="模型厂商" required>
            <a-select
              v-model:value="selectedProvider"
              placeholder="请选择模型厂商"
              style="width: 100%"
            >
              <a-select-option v-for="provider in modelProviders" :key="provider.value" :value="provider.value">
                {{ provider.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
          
          <a-form-item label="模型版本" required>
            <a-select
              v-model:value="selectedModel"
              placeholder="请选择模型版本"
              style="width: 100%"
              :disabled="!selectedProvider"
            >
              <a-select-option v-for="model in currentModels" :key="model" :value="model">
                {{ model }}
              </a-select-option>
            </a-select>
          </a-form-item>
          
          <a-form-item label="API 端点 (Endpoint)" required>
            <a-input
              v-model:value="form.llm_endpoint"
              placeholder="https://api.openai.com/v1"
            />
            <div style="color: #999; font-size: 12px; margin-top: 4px;">
              选择厂商后自动填充，支持手动修改
            </div>
          </a-form-item>
          
          <a-form-item label="API Key" required>
            <a-input-password
              v-model:value="form.llm_api_key"
              placeholder="请输入 API Key"
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
