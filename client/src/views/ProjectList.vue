<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, GithubOutlined, LinkOutlined } from '@ant-design/icons-vue'
import type { Project } from '../types'
import { projectApi } from '../services/api'

const router = useRouter()
const projects = ref<Project[]>([])
const loading = ref(false)
const showModal = ref(false)
const formLoading = ref(false)

const form = ref({
  name: '',
  git_url: '',
  branch: 'main',
  base_url: '',
})

async function loadProjects() {
  loading.value = true
  try {
    projects.value = await projectApi.list()
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!form.value.name || !form.value.git_url || !form.value.base_url) {
    message.warning('请填写完整信息')
    return
  }
  formLoading.value = true
  try {
    await projectApi.create(form.value)
    message.success('项目创建成功')
    showModal.value = false
    form.value = { name: '', git_url: '', branch: 'main', base_url: '' }
    await loadProjects()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    formLoading.value = false
  }
}

async function handleDelete(id: string) {
  try {
    await projectApi.delete(id)
    message.success('项目已删除')
    await loadProjects()
  } catch {
    message.error('删除失败')
  }
}

onMounted(loadProjects)
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0;">项目列表</h2>
      <a-button type="primary" @click="showModal = true">
        <PlusOutlined /> 新建项目
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <a-empty v-if="!loading && projects.length === 0" description="暂无项目，点击右上角创建" />
      <a-row :gutter="[16, 16]">
        <a-col :xs="24" :sm="12" :lg="8" v-for="p in projects" :key="p.id">
          <a-card hoverable @click="router.push(`/project/${p.id}`)">
            <template #title>
              <ProjectOutlined style="margin-right: 8px;" />{{ p.name }}
            </template>
            <template #extra>
              <a-popconfirm title="确定删除该项目？" @confirm.stop="handleDelete(p.id)">
                <a-button type="text" danger size="small" @click.stop>删除</a-button>
              </a-popconfirm>
            </template>
            <p><GithubOutlined /> {{ p.git_url }}</p>
            <p><LinkOutlined /> {{ p.base_url }}</p>
            <p style="color: #999; font-size: 12px;">
              分支: {{ p.branch }} | 创建于 {{ new Date(p.created_at).toLocaleDateString() }}
            </p>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>

    <a-modal v-model:open="showModal" title="新建项目" @ok="handleCreate" :confirmLoading="formLoading">
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="项目名称" required>
          <a-input v-model:value="form.name" placeholder="如：我的电商平台" />
        </a-form-item>
        <a-form-item label="Git 仓库地址" required>
          <a-input v-model:value="form.git_url" placeholder="https://github.com/user/repo.git" />
        </a-form-item>
        <a-form-item label="分支">
          <a-input v-model:value="form.branch" placeholder="main" />
        </a-form-item>
        <a-form-item label="被测站点 URL" required>
          <a-input v-model:value="form.base_url" placeholder="https://example.com" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script lang="ts">
import { ProjectOutlined } from '@ant-design/icons-vue'
export default { components: { ProjectOutlined } }
</script>
