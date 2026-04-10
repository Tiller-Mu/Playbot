export interface Project {
  id: string
  name: string
  git_url: string
  branch: string
  base_url: string
  repo_path: string | null
  created_at: string
  updated_at: string
}

export interface TestCase {
  id: string
  project_id: string
  title: string
  description: string
  script_path: string | null
  script_content: string | null
  group_name: string
  tags: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface Execution {
  id: string
  project_id: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error'
  total_cases: number
  passed_count: number
  failed_count: number
  skipped_count: number
  start_time: string | null
  end_time: string | null
  created_at: string
}

export interface ExecutionDetail {
  id: string
  execution_id: string
  test_case_id: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'skipped'
  error_message: string | null
  screenshot_path: string | null
  duration_ms: number
}

export interface LLMSettings {
  llm_endpoint: string
  llm_api_key: string
  llm_model: string
}
