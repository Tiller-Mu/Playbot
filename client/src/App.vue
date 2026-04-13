<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  ExperimentOutlined,
  SettingOutlined,
  ProjectOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const collapsed = ref(true)

const selectedKeys = computed(() => {
  if (route.path.startsWith('/settings')) return ['settings']
  return ['projects']
})
</script>

<template>
  <a-layout style="min-height: 100vh">
    <a-layout-sider v-model:collapsed="collapsed" collapsible>
      <div style="height: 48px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 16px; font-weight: bold; white-space: nowrap; overflow: hidden;">
        <ExperimentOutlined style="font-size: 20px;" />
        <span v-if="!collapsed" style="margin-left: 8px;">TestPilot</span>
      </div>
      <a-menu theme="dark" :selectedKeys="selectedKeys" mode="inline">
        <a-menu-item key="projects" @click="router.push('/projects')">
          <ProjectOutlined />
          <span>项目管理</span>
        </a-menu-item>
        <a-menu-item key="settings" @click="router.push('/settings')">
          <SettingOutlined />
          <span>系统设置</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-content style="padding: 24px; background: #f5f5f5; min-height: 100%;">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<style>
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}
</style>
