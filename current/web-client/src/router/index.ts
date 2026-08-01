import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useWorkspaceStore } from '../stores/workspace'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/',
      component: () => import('../components/layout/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('../views/DashboardView.vue'),
        },
        {
          path: 'references/works',
          name: 'work-list',
          component: () => import('../views/references/WorkCatalogView.vue'),
        },
        {
          path: 'references/:type',
          name: 'reference-list',
          component: () => import('../views/references/ReferenceView.vue'),
          props: true,
        },
        {
          path: 'documents/estimates',
          name: 'estimate-list',
          component: () => import('../views/documents/EstimateListView.vue'),
        },
        {
          path: 'documents/estimates/new',
          name: 'estimate-create',
          component: () => import('../views/documents/EstimateFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/estimates/:id',
          name: 'estimate-edit',
          component: () => import('../views/documents/EstimateFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        {
          path: 'documents/daily-reports',
          name: 'daily-report-list',
          component: () => import('../views/documents/DailyReportListView.vue'),
        },
        {
          path: 'documents/daily-reports/new',
          name: 'daily-report-create',
          component: () => import('../views/documents/DailyReportFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/daily-reports/:id',
          name: 'daily-report-edit',
          component: () => import('../views/documents/DailyReportFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        {
          path: 'documents/timesheets',
          name: 'timesheet-list',
          component: () => import('../views/documents/TimesheetListView.vue'),
        },
        {
          path: 'documents/timesheets/new',
          name: 'timesheet-create',
          component: () => import('../views/documents/TimesheetFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/timesheets/:id',
          name: 'timesheet-edit',
          component: () => import('../views/documents/TimesheetFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        // Cost accounting — material consumptions
        {
          path: 'documents/material-consumptions',
          name: 'material-consumption-list',
          component: () => import('../views/documents/MaterialConsumptionListView.vue'),
        },
        {
          path: 'documents/material-consumptions/new',
          name: 'material-consumption-create',
          component: () => import('../views/documents/MaterialConsumptionFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/material-consumptions/:id',
          name: 'material-consumption-edit',
          component: () => import('../views/documents/MaterialConsumptionFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        // Cost accounting — machinery usage
        {
          path: 'documents/machinery-usage',
          name: 'machinery-usage-list',
          component: () => import('../views/documents/MachineryUsageListView.vue'),
        },
        {
          path: 'documents/machinery-usage/new',
          name: 'machinery-usage-create',
          component: () => import('../views/documents/MachineryUsageFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/machinery-usage/:id',
          name: 'machinery-usage-edit',
          component: () => import('../views/documents/MachineryUsageFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        // Cost accounting — subcontract acceptances
        {
          path: 'documents/subcontract-acceptances',
          name: 'subcontract-acceptance-list',
          component: () => import('../views/documents/SubcontractAcceptanceListView.vue'),
        },
        {
          path: 'documents/subcontract-acceptances/new',
          name: 'subcontract-acceptance-create',
          component: () => import('../views/documents/SubcontractAcceptanceFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/subcontract-acceptances/:id',
          name: 'subcontract-acceptance-edit',
          component: () => import('../views/documents/SubcontractAcceptanceFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        // Cost accounting — overhead expenses
        {
          path: 'documents/overhead-expenses',
          name: 'overhead-expense-list',
          component: () => import('../views/documents/OverheadExpenseListView.vue'),
        },
        {
          path: 'documents/overhead-expenses/new',
          name: 'overhead-expense-create',
          component: () => import('../views/documents/OverheadExpenseFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/overhead-expenses/:id',
          name: 'overhead-expense-edit',
          component: () => import('../views/documents/OverheadExpenseFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        // Cost accounting — cost calculations
        {
          path: 'documents/cost-calculations',
          name: 'cost-calculation-list',
          component: () => import('../views/documents/CostCalculationListView.vue'),
        },
        {
          path: 'documents/cost-calculations/new',
          name: 'cost-calculation-create',
          component: () => import('../views/documents/CostCalculationFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'documents/cost-calculations/:id',
          name: 'cost-calculation-edit',
          component: () => import('../views/documents/CostCalculationFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        // Cost accounting — reports
        {
          path: 'reports/cost-card',
          name: 'cost-card-report',
          component: () => import('../views/reports/CostCardView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'reports/cost-turnover',
          name: 'cost-turnover-report',
          component: () => import('../views/reports/CostTurnoverView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'reports/cost-deviations',
          name: 'cost-deviations-report',
          component: () => import('../views/reports/CostDeviationsView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'reports/cost-profitability',
          name: 'cost-profitability-report',
          component: () => import('../views/reports/CostProfitabilityView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'registers/work-execution',
          name: 'work-execution-register',
          component: () => import('../views/registers/WorkExecutionView.vue'),
        },
        {
          path: 'reports/inventory-balances',
          name: 'inventory-balances-report',
          component: () => import('../views/reports/InventoryBalancesReport.vue'),
        },
        {
          path: 'reports/settlements-turnover',
          name: 'settlements-turnover-report',
          component: () => import('../views/reports/SettlementsTurnoverReport.vue'),
        },
        {
          path: 'reports/overdue',
          name: 'overdue-report',
          component: () => import('../views/reports/OverdueReport.vue'),
        },
        {
          path: 'settings/import-profiles',
          name: 'import-profiles',
          component: () => import('../views/admin/ImportProfilesView.vue'),
        },
        {
          path: 'payments/schedules',
          name: 'payment-schedule-list',
          component: () => import('../views/payments/PaymentScheduleListView.vue'),
        },
        {
          path: 'payments/schedules/new',
          name: 'payment-schedule-create',
          component: () => import('../views/payments/PaymentScheduleFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'payments/schedules/:id',
          name: 'payment-schedule-edit',
          component: () => import('../views/payments/PaymentScheduleFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        {
          path: 'payments/calendar',
          name: 'payment-calendar',
          component: () => import('../views/payments/PaymentCalendarView.vue'),
        },
        {
          path: 'payments/transactions',
          name: 'payment-transaction-list',
          component: () => import('../views/payments/PaymentTransactionListView.vue'),
        },
        {
          path: 'goods/receipts',
          name: 'goods-receipt-list',
          component: () => import('../views/goods/GoodsDocumentListView.vue'),
          props: { kind: 'receipt' },
        },
        {
          path: 'goods/receipts/new',
          name: 'goods-receipt-create',
          component: () => import('../views/goods/GoodsDocumentFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'goods/receipts/:id',
          name: 'goods-receipt-edit',
          component: () => import('../views/goods/GoodsDocumentFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        {
          path: 'goods/issues',
          name: 'goods-issue-list',
          component: () => import('../views/goods/GoodsDocumentListView.vue'),
          props: { kind: 'issue' },
        },
        {
          path: 'goods/issues/new',
          name: 'goods-issue-create',
          component: () => import('../views/goods/GoodsDocumentFormView.vue'),
          meta: { workspace: true },
        },
        {
          path: 'goods/issues/:id',
          name: 'goods-issue-edit',
          component: () => import('../views/goods/GoodsDocumentFormView.vue'),
          props: true,
          meta: { workspace: true },
        },
        {
          path: 'sync',
          name: 'sync',
          component: () => import('../views/SyncView.vue'),
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.initialize()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }

  return true
})

// Синхронизация табов рабочего пространства с текущим маршрутом.
router.afterEach((to) => {
  if (to.meta.requiresAuth) {
    const workspace = useWorkspaceStore()
    workspace.syncFromRoute(to)
  }
})

// Предупреждение при закрытии вкладки браузера с несохранёнными изменениями.
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', (event) => {
    try {
      const workspace = useWorkspaceStore()
      if (workspace.hasDirty) {
        event.preventDefault()
        event.returnValue = ''
      }
    } catch {
      // store может быть не инициализирован — игнорируем
    }
  })
}

export default router
