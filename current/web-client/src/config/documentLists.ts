/**
 * Конфигурации списков документов для всех 11 видов (DOCUMENT_LIST_SPEC.md, раздел 5.2 / 3.6).
 * Каждый вид описывается одним DocListConfig; поведение списка едино и управляется
 * useDocumentList. Здесь — только данные: колонки, API, маршруты, «Ввод на основании».
 */
import type { DocListConfig, DocListColumn, DocListRow } from './documentListTypes'
import * as docs from '../api/documents'
import * as cost from '../api/costAccounting'
import * as goodsApi from '../api/goods'
import * as pay from '../api/payments'

// Общие опции фильтра статуса проведения
const postedFilterOptions = [
  { value: '1', label: 'Проведён' },
  { value: '0', label: 'Черновик' },
]

type RoleUser = { role?: string; person_id?: number | null } | null

function canManageCostOffice(user: RoleUser): boolean {
  return user?.role === 'admin' || user?.role === 'manager'
}

function canPrepareFieldCost(user: RoleUser): boolean {
  return canManageCostOffice(user) || user?.role === 'foreman'
}

function canDeleteFieldCost(user: RoleUser, row: DocListRow): boolean {
  if (canManageCostOffice(user)) return true
  return user?.role === 'foreman'
    && !!user.person_id
    && Number(row.foreman_id) === user.person_id
}

function baseColumns(extra: DocListColumn[]): DocListColumn[] {
  return [
    { key: 'number', label: 'Номер', sortable: true, filterable: true, filter: { type: 'text', placeholder: '№' } },
    { key: 'date', label: 'Дата', sortable: true, filterable: true, filter: { type: 'date' } },
    ...extra,
  ]
}

// ── 1. Сметы ────────────────────────────────────────────────────────────
export const estimateListConfig: DocListConfig = {
  formName: 'estimates',
  title: 'Сметы',
  createLabel: 'Создать смету',
  createRoute: '/documents/estimates/new',
  itemRoute: (id) => `/documents/estimates/${id}`,
  defaultSort: { key: 'date', order: 'desc' },
  api: {
    list: (p) => docs.listEstimates(p),
    post: docs.postEstimate,
    unpost: docs.unpostEstimate,
    remove: docs.deleteEstimate,
    restore: docs.restoreEstimate,
    copy: docs.copyEstimate,
  },
  columns: baseColumns([
    { key: 'customer_name', label: 'Заказчик', filterable: true, filter: { type: 'text' } },
    { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
    { key: 'total_sum', label: 'Сумма', sortable: true },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ]),
  baseOn: [
    { kind: 'daily-reports', label: 'Дневной отчёт', createRoute: '/documents/daily-reports/new' },
    { kind: 'timesheets', label: 'Табель', createRoute: '/documents/timesheets/new' },
    { kind: 'material-consumptions', label: 'Расход материалов', createRoute: '/documents/material-consumptions/new' },
    { kind: 'machinery-usage', label: 'Рапорт машин', createRoute: '/documents/machinery-usage/new' },
    { kind: 'payment-schedules', label: 'Платёжный календарь', createRoute: '/payments/schedules/new' },
  ],
  labels: { one: 'смету', few: 'сметы', many: 'смет' },
}

// ── 2. Отчёты прораба ───────────────────────────────────────────────────
export const dailyReportListConfig: DocListConfig = {
  formName: 'daily-reports',
  title: 'Отчёты прораба',
  createLabel: 'Создать отчёт',
  createRoute: '/documents/daily-reports/new',
  itemRoute: (id) => `/documents/daily-reports/${id}`,
  defaultSort: { key: 'date', order: 'desc' },
  api: {
    list: (p) => docs.listDailyReports(p),
    post: docs.postDailyReport,
    unpost: docs.unpostDailyReport,
    remove: docs.deleteDailyReport,
    restore: docs.restoreDailyReport,
    copy: docs.copyDailyReport,
  },
  columns: baseColumns([
    { key: 'estimate_number', label: 'Смета', filterable: true, filter: { type: 'text' } },
    { key: 'foreman_name', label: 'Прораб', filterable: true, filter: { type: 'text' } },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ]),
  labels: { one: 'отчёт', few: 'отчёта', many: 'отчётов' },
}

// ── 3. Табели ───────────────────────────────────────────────────────────
export const timesheetListConfig: DocListConfig = {
  formName: 'timesheets',
  title: 'Табели',
  createLabel: 'Создать табель',
  createRoute: '/documents/timesheets/new',
  itemRoute: (id) => `/documents/timesheets/${id}`,
  defaultSort: { key: 'date', order: 'desc' },
  canManagePosting: (user, row) => {
    if (user?.role === 'admin') return true
    // Бригадир управляет только своими табелями.
    return user?.role === 'foreman' && !!row.foreman_id && row.foreman_id === user?.person_id
  },
  api: {
    list: (p) => docs.listTimesheets(p),
    post: docs.postTimesheet,
    unpost: docs.unpostTimesheet,
    remove: docs.deleteTimesheet,
    copy: docs.copyTimesheet,
  },
  columns: baseColumns([
    { key: 'month_year', label: 'Период', sortable: true, filterable: true, filter: { type: 'month' } },
    { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
    { key: 'estimate_number', label: 'Смета', filterable: true, filter: { type: 'text' } },
    { key: 'foreman_name', label: 'Бригадир', filterable: true, filter: { type: 'text' } },
    { key: 'total_hours', label: 'Часы', sortable: true },
    { key: 'total_amount', label: 'Сумма', sortable: true },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ]),
  labels: { one: 'табель', few: 'табеля', many: 'табелей' },
}

// ── 4. Расход материалов ────────────────────────────────────────────────
export const materialConsumptionListConfig: DocListConfig = {
  formName: 'material-consumptions',
  title: 'Расход материалов',
  createLabel: 'Расход материалов',
  createRoute: '/documents/material-consumptions/new',
  itemRoute: (id) => `/documents/material-consumptions/${id}`,
  defaultSort: { key: 'date', order: 'desc' },
  canCreate: canPrepareFieldCost,
  canManagePosting: canManageCostOffice,
  canDelete: canDeleteFieldCost,
  api: {
    list: (p) => cost.listMaterialConsumptions(p),
    post: cost.postMaterialConsumption,
    unpost: cost.unpostMaterialConsumption,
    remove: cost.deleteMaterialConsumption,
    restore: cost.restoreMaterialConsumption,
  },
  columns: baseColumns([
    { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
    { key: 'estimate_number', label: 'Смета', filterable: true, filter: { type: 'text' } },
    { key: 'warehouse', label: 'Склад' },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ]),
  labels: { one: 'документ', few: 'документа', many: 'документов' },
}

// ── 5. Рапорты о работе машин ───────────────────────────────────────────
export const machineryUsageListConfig: DocListConfig = {
  formName: 'machinery-usage',
  title: 'Рапорты о работе машин',
  createLabel: 'Рапорт машин',
  createRoute: '/documents/machinery-usage/new',
  itemRoute: (id) => `/documents/machinery-usage/${id}`,
  defaultSort: { key: 'date', order: 'desc' },
  canCreate: canPrepareFieldCost,
  canManagePosting: canManageCostOffice,
  canDelete: canDeleteFieldCost,
  api: {
    list: (p) => cost.listMachineryUsageReports(p),
    post: cost.postMachineryUsageReport,
    unpost: cost.unpostMachineryUsageReport,
    remove: cost.deleteMachineryUsageReport,
    restore: cost.restoreMachineryUsageReport,
  },
  columns: baseColumns([
    { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
    { key: 'estimate_number', label: 'Смета', filterable: true, filter: { type: 'text' } },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ]),
  labels: { one: 'рапорт', few: 'рапорта', many: 'рапортов' },
}

// ── 6. Акты приёмки субподрядных работ ──────────────────────────────────
export const subcontractAcceptanceListConfig: DocListConfig = {
  formName: 'subcontract-acceptances',
  title: 'Акты приёмки субподрядных работ',
  createLabel: 'Акт субподряда',
  createRoute: '/documents/subcontract-acceptances/new',
  itemRoute: (id) => `/documents/subcontract-acceptances/${id}`,
  defaultSort: { key: 'date', order: 'desc' },
  canCreate: canManageCostOffice,
  canManagePosting: canManageCostOffice,
  canDelete: (user) => canManageCostOffice(user),
  api: {
    list: (p) => cost.listSubcontractAcceptances(p),
    post: cost.postSubcontractAcceptance,
    unpost: cost.unpostSubcontractAcceptance,
    remove: cost.deleteSubcontractAcceptance,
    restore: cost.restoreSubcontractAcceptance,
  },
  columns: baseColumns([
    { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
    { key: 'estimate_number', label: 'Смета', filterable: true, filter: { type: 'text' } },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ]),
  labels: { one: 'акт', few: 'акта', many: 'актов' },
}

// ── 7. Накладные расходы ────────────────────────────────────────────────
export const overheadExpenseListConfig: DocListConfig = {
  formName: 'overhead-expenses',
  title: 'Накладные расходы',
  createLabel: 'Накладные расходы',
  createRoute: '/documents/overhead-expenses/new',
  itemRoute: (id) => `/documents/overhead-expenses/${id}`,
  defaultSort: { key: 'period', order: 'desc' },
  hasPost: false, // статус — is_distributed; проведение отсутствует
  canCreate: canManageCostOffice,
  canDelete: (user) => canManageCostOffice(user),
  api: {
    list: (p) => cost.listOverheadExpenses(p),
    remove: cost.deleteOverheadExpense,
    restore: cost.restoreOverheadExpense,
  },
  columns: baseColumns([
    { key: 'period', label: 'Период', sortable: true, filterable: true, filter: { type: 'month' } },
    { key: 'is_distributed', label: 'Статус' },
  ]),
  labels: { one: 'документ', few: 'документа', many: 'документов' },
}

// ── 8. Расчёты себестоимости ────────────────────────────────────────────
export const costCalculationListConfig: DocListConfig = {
  formName: 'cost-calculations',
  title: 'Расчёты себестоимости',
  createLabel: 'Расчёт себестоимости',
  createRoute: '/documents/cost-calculations/new',
  itemRoute: (id) => `/documents/cost-calculations/${id}`,
  defaultSort: { key: 'period', order: 'desc' },
  canCreate: canManageCostOffice,
  canManagePosting: canManageCostOffice,
  canDelete: (user) => canManageCostOffice(user),
  statusField: 'status',
  postableWhen: (row) => row.status === 'calculated',
  postedWhen: (row) => row.status === 'posted',
  canDeleteWhen: (row) => row.status !== 'posted',
  api: {
    list: (p) => cost.listCostCalculations(p),
    post: cost.postCostCalculation,
    unpost: cost.unpostCostCalculation,
    remove: cost.deleteCostCalculation,
    restore: cost.restoreCostCalculation,
  },
  columns: baseColumns([
    { key: 'period', label: 'Период', sortable: true, filterable: true, filter: { type: 'month' } },
    { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
    { key: 'status', label: 'Статус' },
  ]),
  labels: { one: 'расчёт', few: 'расчёта', many: 'расчётов' },
}

// ── 9. ТМЦ (поступления / списания) ─────────────────────────────────────
export function goodsDocumentListConfig(kind: 'receipt' | 'issue'): DocListConfig {
  const isReceipt = kind === 'receipt'
  const basePath = isReceipt ? '/goods/receipts' : '/goods/issues'
  return {
    formName: isReceipt ? 'goods-receipts' : 'goods-issues',
    title: isReceipt ? 'Поступления ТМЦ' : 'Списания ТМЦ',
    createLabel: isReceipt ? 'Создать поступление' : 'Создать списание',
    createRoute: `${basePath}/new`,
    itemRoute: (id) => `${basePath}/${id}`,
    defaultSort: { key: 'date', order: 'desc' },
    api: {
      list: (p) => goodsApi.listGoodsDocuments(kind, p),
      post: (id) => goodsApi.postGoodsDocument(kind, id),
      unpost: (id) => goodsApi.unpostGoodsDocument(kind, id),
      remove: (id) => goodsApi.deleteGoodsDocument(kind, id),
      copy: (id) => goodsApi.copyGoodsDocument(kind, id),
    },
    columns: baseColumns([
      { key: 'organization_name', label: 'Организация' },
      { key: 'warehouse_name', label: 'Склад', filterable: true, filter: { type: 'text' } },
      { key: 'counterparty_name', label: isReceipt ? 'Поставщик' : 'Покупатель', filterable: true, filter: { type: 'text' } },
      { key: 'contract_number', label: 'Договор', filterable: true, filter: { type: 'text' } },
      { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
      { key: 'sum_without_vat', label: 'Сумма без НДС', sortable: true },
      { key: 'sum_with_vat', label: 'С НДС', sortable: true },
      { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
    ]),
    baseOn: isReceipt
      ? [{ kind: 'goods-issues', label: 'Списание ТМЦ', createRoute: '/goods/issues/new' }]
      : undefined,
    labels: { one: 'документ', few: 'документа', many: 'документов' },
  }
}

// ── 10. Платёжные календари ─────────────────────────────────────────────
export const paymentScheduleListConfig: DocListConfig = {
  formName: 'payment-schedules',
  title: 'Платёжные календари',
  createLabel: 'Создать календарь',
  createRoute: '/payments/schedules/new',
  itemRoute: (id) => `/payments/schedules/${id}`,
  defaultSort: { key: 'date_from', order: 'desc' },
  api: {
    list: (p) => pay.listPaymentSchedules(p),
    post: pay.postPaymentSchedule,
    unpost: pay.unpostPaymentSchedule,
    remove: pay.deletePaymentSchedule,
  },
  columns: [
    { key: 'number', label: 'Номер', sortable: true, filterable: true, filter: { type: 'text', placeholder: '№' } },
    { key: 'date_from', label: 'Период с', sortable: true, filterable: true, filter: { type: 'date' } },
    { key: 'date_to', label: 'Период по' },
    { key: 'object_name', label: 'Объект', filterable: true, filter: { type: 'text' } },
    { key: 'contract_number', label: 'Договор', filterable: true, filter: { type: 'text' } },
    { key: 'total_incoming', label: 'Поступления', sortable: true },
    { key: 'total_outgoing', label: 'Платежи', sortable: true },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ],
  labels: { one: 'календарь', few: 'календаря', many: 'календарей' },
}

// ── 11. Платежи (факт) ──────────────────────────────────────────────────
export const paymentTransactionListConfig: DocListConfig = {
  formName: 'payment-transactions',
  title: 'Платежи (факт)',
  createLabel: '+ Платёж',
  createRoute: '', // нет роута формы — создание инлайн в view
  itemRoute: () => '', // отдельной формы нет
  canOpen: false,
  defaultSort: { key: 'date', order: 'desc' },
  api: {
    list: (p) => pay.listPaymentTransactions(p),
    post: pay.postPaymentTransaction,
    unpost: pay.unpostPaymentTransaction,
    remove: pay.deletePaymentTransaction,
  },
  columns: baseColumns([
    { key: 'direction', label: 'Направление', filterable: true, filter: { type: 'select', options: [{ value: 'incoming', label: 'Поступление' }, { value: 'outgoing', label: 'Платёж' }] } },
    { key: 'category', label: 'Категория' },
    { key: 'counterparty_name', label: 'Контрагент', filterable: true, filter: { type: 'text' } },
    { key: 'amount', label: 'Сумма', sortable: true },
    { key: 'is_posted', label: 'Статус', filterable: true, filter: { type: 'select', options: postedFilterOptions } },
  ]),
  labels: { one: 'платёж', few: 'платежа', many: 'платежей' },
}
