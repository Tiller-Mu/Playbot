import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Project } from '../types'
import { projectApi } from '../services/api'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)

  async function loadProjects() {
    loading.value = true
    try {
      projects.value = await projectApi.list()
    } finally {
      loading.value = false
    }
  }

  async function loadProject(id: string) {
    loading.value = true
    try {
      currentProject.value = await projectApi.get(id)
    } finally {
      loading.value = false
    }
  }

  return { projects, currentProject, loading, loadProjects, loadProject }
})
