import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/projects',
    },
    {
      path: '/projects',
      name: 'Projects',
      component: () => import('../views/ProjectList.vue'),
    },
    {
      path: '/project/:id',
      name: 'ProjectDetail',
      component: () => import('../views/ProjectDetail.vue'),
      children: [
        {
          path: '',
          name: 'TestCases',
          component: () => import('../views/TestCaseList.vue'),
        },
        {
          path: 'executions',
          name: 'Executions',
          component: () => import('../views/ExecutionHistory.vue'),
        },
      ],
    },
    {
      path: '/testcase/:id',
      name: 'TestCaseEdit',
      component: () => import('../views/TestCaseEdit.vue'),
    },
    {
      path: '/execution/:id',
      name: 'ExecutionDetail',
      component: () => import('../views/ExecutionView.vue'),
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('../views/SettingsView.vue'),
    },
  ],
})

export default router
