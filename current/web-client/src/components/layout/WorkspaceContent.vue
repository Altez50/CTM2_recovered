<template>
  <div class="workspace-content">
    <div
      v-for="tab in workspace.tabs"
      :key="tab.id"
      v-show="tab.id === workspace.activeId"
      class="workspace-pane"
      :data-tab-id="tab.id"
      :data-kind="tab.kind"
    >
      <component
        :is="resolveComponent(tab.kind)"
        v-bind="resolveProps(tab)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, shallowRef, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore, type WorkspaceTab } from '../../stores/workspace'

const workspace = useWorkspaceStore()
const router = useRouter()

// Карта kind -> ленивый компонент. shallowRef: компоненты не реактивны.
const componentMap = shallowRef<Record<string, Component>>({
  'sale-list': defineAsyncComponent(() => import('../../views/sales/SaleListView.vue')),
  'sale-form': defineAsyncComponent(() => import('../../views/sales/SaleFormView.vue')),
  'purchase-list': defineAsyncComponent(() => import('../../views/purchases/PurchaseListView.vue')),
  'purchase-form': defineAsyncComponent(() => import('../../views/purchases/PurchaseFormView.vue')),
  dashboard: defineAsyncComponent(() => import('../../views/DashboardView.vue')),
  'estimate-list': defineAsyncComponent(() => import('../../views/documents/EstimateListView.vue')),
  'estimate-form': defineAsyncComponent(() => import('../../views/documents/EstimateFormView.vue')),
  'daily-report-list': defineAsyncComponent(() => import('../../views/documents/DailyReportListView.vue')),
  'daily-report-form': defineAsyncComponent(() => import('../../views/documents/DailyReportFormView.vue')),
  'timesheet-list': defineAsyncComponent(() => import('../../views/documents/TimesheetListView.vue')),
  'timesheet-form': defineAsyncComponent(() => import('../../views/documents/TimesheetFormView.vue')),
  'work-execution-register': defineAsyncComponent(() => import('../../views/registers/WorkExecutionView.vue')),
  'inventory-balances-report': defineAsyncComponent(() => import('../../views/reports/InventoryBalancesReport.vue')),
  'settlements-turnover-report': defineAsyncComponent(() => import('../../views/reports/SettlementsTurnoverReport.vue')),
  'overdue-report': defineAsyncComponent(() => import('../../views/reports/OverdueReport.vue')),
  'import-profiles': defineAsyncComponent(() => import('../../views/admin/ImportProfilesView.vue')),
  'payment-schedule-list': defineAsyncComponent(() => import('../../views/payments/PaymentScheduleListView.vue')),
  'payment-schedule-form': defineAsyncComponent(() => import('../../views/payments/PaymentScheduleFormView.vue')),
  'payment-calendar': defineAsyncComponent(() => import('../../views/payments/PaymentCalendarView.vue')),
  'payment-transaction-list': defineAsyncComponent(() => import('../../views/payments/PaymentTransactionListView.vue')),
  'goods-receipt-list': defineAsyncComponent(() => import('../../views/goods/GoodsDocumentListView.vue')),
  'goods-receipt-form': defineAsyncComponent(() => import('../../views/goods/GoodsDocumentFormView.vue')),
  'goods-issue-list': defineAsyncComponent(() => import('../../views/goods/GoodsDocumentListView.vue')),
  'goods-issue-form': defineAsyncComponent(() => import('../../views/goods/GoodsDocumentFormView.vue')),
  'goods-price-adjustment-list': defineAsyncComponent(() => import('../../views/goods/GoodsPriceAdjustmentListView.vue')),
  'opening-balance-list': defineAsyncComponent(() => import('../../views/goods/OpeningBalanceListView.vue')),
  'opening-balance-form': defineAsyncComponent(() => import('../../views/goods/OpeningBalanceFormView.vue')),
  'inventory-turnover-report': defineAsyncComponent(() => import('../../views/reports/InventoryTurnoverReport.vue')),
  'goods-price-adjustment-form': defineAsyncComponent(() => import('../../views/goods/GoodsPriceAdjustmentFormView.vue')),
  'goods-return-list': defineAsyncComponent(() => import('../../views/goods/GoodsReturnListView.vue')),
  'goods-return-form': defineAsyncComponent(() => import('../../views/goods/GoodsReturnFormView.vue')),
  'goods-transfer-list': defineAsyncComponent(() => import('../../views/goods/GoodsTransferListView.vue')),
  'goods-transfer-form': defineAsyncComponent(() => import('../../views/goods/GoodsTransferFormView.vue')),
  // Cost accounting documents
  'material-consumption-list': defineAsyncComponent(() => import('../../views/documents/MaterialConsumptionListView.vue')),
  'material-consumption-form': defineAsyncComponent(() => import('../../views/documents/MaterialConsumptionFormView.vue')),
  'machinery-usage-list': defineAsyncComponent(() => import('../../views/documents/MachineryUsageListView.vue')),
  'machinery-usage-form': defineAsyncComponent(() => import('../../views/documents/MachineryUsageFormView.vue')),
  'subcontract-acceptance-list': defineAsyncComponent(() => import('../../views/documents/SubcontractAcceptanceListView.vue')),
  'subcontract-acceptance-form': defineAsyncComponent(() => import('../../views/documents/SubcontractAcceptanceFormView.vue')),
  'overhead-expense-list': defineAsyncComponent(() => import('../../views/documents/OverheadExpenseListView.vue')),
  'overhead-expense-form': defineAsyncComponent(() => import('../../views/documents/OverheadExpenseFormView.vue')),
  'cost-calculation-list': defineAsyncComponent(() => import('../../views/documents/CostCalculationListView.vue')),
  'cost-calculation-form': defineAsyncComponent(() => import('../../views/documents/CostCalculationFormView.vue')),
  // Cost accounting reports
  'cost-card-report': defineAsyncComponent(() => import('../../views/reports/CostCardView.vue')),
  'cost-turnover-report': defineAsyncComponent(() => import('../../views/reports/CostTurnoverView.vue')),
  'cost-deviations-report': defineAsyncComponent(() => import('../../views/reports/CostDeviationsView.vue')),
  'cost-profitability-report': defineAsyncComponent(() => import('../../views/reports/CostProfitabilityView.vue')),
  'work-catalog': defineAsyncComponent(() => import('../../views/references/WorkCatalogView.vue')),
  'reference-list': defineAsyncComponent(() => import('../../views/references/ReferenceView.vue')),
  'sync': defineAsyncComponent(() => import('../../views/SyncView.vue')),
  'user-access': defineAsyncComponent(() => import('../../views/UserAccessView.vue')),
})

function resolveComponent(kind: WorkspaceTab['kind']): Component {
  return componentMap.value[kind] ?? componentMap.value.dashboard
}

function resolveProps(tab: WorkspaceTab): Record<string, unknown> {
  // tabId нужен виду для регистрации заголовка/тулбара в глобальном хидере.
  const props: Record<string, unknown> = { tabId: tab.id }
  // Формы документов принимают :id
  if (tab.params.id) {
    props.id = tab.params.id
  }
  // Справочник принимает :type
  if (tab.params.type) {
    props.type = tab.params.type
  }
  if (tab.params.purchaseKind) props.kind = tab.params.purchaseKind
  if (tab.params.saleKind) props.kind = tab.params.saleKind
  // ТМЦ-формы параметризуются типом документа (kind) по виду таба,
  // т.к. router.props игнорируется в MDI-рендере.
  if (tab.kind === 'goods-receipt-list' || tab.kind === 'goods-receipt-form') {
    props.kind = 'receipt'
  } else if (tab.kind === 'goods-issue-list' || tab.kind === 'goods-issue-form') {
    props.kind = 'issue'
  }
  return props
}

// Обработка запросов навигации от стора (декаплинг от инстанса роутера).
watch(
  () => workspace.pendingNavigation,
  (target) => {
    if (!target) return
    const current = router.currentRoute.value
    // Предотвращаем лишние пуши, если URL уже соответствует.
    if (
      current.name === target.name &&
      JSON.stringify(current.params) === JSON.stringify(target.params ?? {})
    ) {
      workspace.consumeNavigation()
      return
    }
    router
      .push({ name: target.name, params: target.params ?? {} })
      .catch(() => {
        /* навигация отменена пользователем/гардом — игнорируем */
      })
      .finally(() => workspace.consumeNavigation())
  },
)
</script>

<style scoped>
.workspace-content {
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  display: flex;
}

.workspace-pane {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
}

.workspace-pane > :deep(*) {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
}
</style>
