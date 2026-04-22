import axios from 'axios'
import type { Project, TestCase, Execution, ExecutionDetail, LLMSettings, TestPage } from '../types'

const api = axios.create({ baseURL: 'http://localhost:8004/api' })

// ---- Project ----
export const projectApi = {
  list: () => api.get<Project[]>('/project').then(r => r.data),
  get: (id: string) => api.get<Project>(`/project/${id}`).then(r => r.data),
  create: (data: { name: string; git_url: string; branch: string; base_url: string }) =>
    api.post<Project>('/project', data).then(r => r.data),
  update: (id: string, data: Partial<Project>) =>
    api.put<Project>(`/project/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/project/${id}`),
  clone: (id: string) => api.post<{ message: string; repo_path: string }>(`/project/${id}/clone`).then(r => r.data),
  pull: (id: string) => api.post<{ message: string }>(`/project/${id}/pull`).then(r => r.data),
  getBranches: (id: string) => api.get<{ branches: string[] }>(`/project/${id}/branches`).then(r => r.data),
}

// ---- Pages ----
export const pageApi = {
  getTree: (projectId: string) => 
    api.get<{ pages: TestPage[]; total_cases: number }>(`/pages/${projectId}`).then(r => r.data),
  refresh: (projectId: string) => 
    api.post<{ pages: TestPage[]; total_cases: number; message: string }>(`/pages/${projectId}/refresh`).then(r => r.data),
  generateCases: (pageId: string) => 
    api.post<TestCase[]>(`/pages/${pageId}/generate`).then(r => r.data),
  getCases: (pageId: string) => 
    api.get<TestCase[]>(`/pages/${pageId}/cases`).then(r => r.data),
  // 获取页面的录制行为轨迹
  getTraces: (pageId: string) => 
    api.get<any[]>(`/pages/${pageId}/traces`).then(r => r.data),
  // 智能体生成用例（LangGraph）
  generateWithAgent: (pageId: string) => 
    api.post<{
      status: string;
      page_id: string;
      page_path: string;
      generated_count: number;
      test_cases: TestCase[];
      analysis: {
        code: string;
        dom: string;
        strategy: string;
      };
      logs: { level: string; message: string; time: string }[];
    }>(`/pages/${pageId}/generate-agent`).then(r => r.data),
}

// ---- TestCase ----
export const testcaseApi = {
  list: (projectId: string, params?: { group_name?: string; enabled?: boolean; search?: string }) =>
    api.get<TestCase[]>('/testcase', { params: { project_id: projectId, ...params } }).then(r => r.data),
  get: (id: string) => api.get<TestCase>(`/testcase/${id}`).then(r => r.data),
  create: (data: { project_id: string; title: string; description: string; script_content?: string; group_name?: string }) =>
    api.post<TestCase>('/testcase', data).then(r => r.data),
  update: (id: string, data: Partial<TestCase>) =>
    api.put<TestCase>(`/testcase/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/testcase/${id}`),
  nlEdit: (id: string, instruction: string) =>
    api.post<{ description: string; script_content: string }>(`/testcase/${id}/edit`, { instruction }).then(r => r.data),
}

// ---- Generate ----
export const generateApi = {
  generate: (projectId: string) =>
    api.post<TestCase[]>('/generate', { project_id: projectId }).then(r => r.data),
  // MCP 页面嗅探（静态分析）
  mcpDiscover: (projectId: string) =>
    api.post<{ message: string; page_count: number; pages: any[] }>('/generate/mcp/discover', { project_id: projectId }).then(r => r.data),
  // 获取组件列表
  getComponents: (projectId: string) =>
    api.get<{ components: any[]; page_components: any[]; common_components: any[]; framework: string; entry_points: string[] }>(`/generate/components/${projectId}`).then(r => r.data),
}

// ---- Execute ----
export const executeApi = {
  run: (caseIds: string[], headless = true) =>
    api.post<Execution>('/execute', { case_ids: caseIds, headless }).then(r => r.data),
  get: (id: string) => api.get<Execution>(`/execute/${id}`).then(r => r.data),
  details: (id: string) => api.get<ExecutionDetail[]>(`/execute/${id}/details`).then(r => r.data),
  history: (projectId: string, limit = 20) =>
    api.get<Execution[]>('/execute/history', { params: { project_id: projectId, limit } }).then(r => r.data),
}

// ---- Settings ----
export const settingsApi = {
  getLLM: () => api.get<LLMSettings>('/settings/llm').then(r => r.data),
  updateLLM: (data: LLMSettings) => api.put<LLMSettings>('/settings/llm', data).then(r => r.data),
  verifyLLM: (data: { llm_endpoint: string; llm_api_key: string; llm_model: string }) => 
    api.post<{ success: boolean; message: string; model: string; interaction_log: any[] }>('/settings/llm/verify', data).then(r => r.data),
}

// ---- Recording ----
export const recordingApi = {
  start: (projectId: string) =>
    api.post<{ message: string; status: string; discovered_count: number }>(`/recording/${projectId}/start`).then(r => r.data),
  pause: (projectId: string) =>
    api.post<{ message: string; status: string; discovered_count: number }>(`/recording/${projectId}/pause`).then(r => r.data),
  stop: (projectId: string) =>
    api.post<{ message: string; status: string; report: any }>(`/recording/${projectId}/stop`).then(r => r.data),
  getStatus: (projectId: string) =>
    api.get<{ status: string; action_count: number; actions: any[]; duration: number }>(`/recording/${projectId}/status`).then(r => r.data),
  capture: (projectId: string, url: string) =>
    api.post<{ message: string; route_pattern: string; total_discovered: number }>(`/recording/${projectId}/capture`, { url }).then(r => r.data),
  clearSession: (projectId: string) =>
    api.delete<{ message: string }>(`/recording/${projectId}/session`).then(r => r.data),
}
