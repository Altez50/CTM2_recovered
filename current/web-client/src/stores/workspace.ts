import { defineStore } from 'pinia'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

/** Описание маршрута для навигации (декаплинг стора от экземпляра роутера). */
export interface NavigationTarget {
  name: string
  params?: Record<string, string | undefined>
}

/**
 * Многодокументный интерфейс (MDI) для веб-клиента.
 *
 * Хранит набор открытых табов-документов, источник правды для того,
 * что сейчас открыто. Роутер используется только для:
 *  - авторизации (guards)
 *  - deep-linking (URL отражает активный таб)
 *  - первичной синхронизации таб <-> маршрут
 *
 * Содержимое табов рендерится отдельным компонентом WorkspaceContent
 * (мультиинстанс через v-for + v-show), а не через <RouterView/>, что позволяет
 * одновременно держать несколько экземпляров одного типа с разными фильтрами.
 */

export type DocumentKind =
  | 'purchase-list'
  | 'sale-list'
  | 'sale-form'
  | 'purchase-form'
  | 'user-access'
  | 'dashboard'
  | 'estimate-list'
  | 'estimate-form'
  | 'daily-report-list'
  | 'daily-report-form'
  | 'timesheet-list'
  | 'timesheet-form'
  | 'work-execution-register'
  | 'payment-schedule-list'
  | 'payment-schedule-form'
  | 'payment-calendar'
  | 'payment-transaction-list'
  | 'goods-receipt-list'
  | 'goods-receipt-form'
  | 'goods-issue-list'
  | 'goods-issue-form'
  | 'goods-price-adjustment-list'
  | 'opening-balance-list'
  | 'opening-balance-form'
  | 'inventory-turnover-report'
  | 'goods-price-adjustment-form'
  | 'goods-return-list'
  | 'goods-return-form'
  | 'goods-transfer-list'
  | 'goods-transfer-form'
  | 'material-consumption-list'
  | 'material-consumption-form'
  | 'machinery-usage-list'
  | 'machinery-usage-form'
  | 'subcontract-acceptance-list'
  | 'subcontract-acceptance-form'
  | 'overhead-expense-list'
  | 'overhead-expense-form'
  | 'cost-calculation-list'
  | 'cost-calculation-form'
  | 'cost-card-report'
  | 'cost-turnover-report'
  | 'cost-deviations-report'
  | 'cost-profitability-report'
  | 'inventory-balances-report'
  | 'settlements-turnover-report'
  | 'overdue-report'
  | 'import-profiles'
  | 'reference-list'
  | 'work-catalog'
  | 'sync'

export interface WorkspaceTab {
  /** Стабильный идентификатор: `${kind}` | `${kind}:${entityId}` | `${kind}#${instanceId}` */
  id: string
  kind: DocumentKind
  title: string
  /** Имя маршрута vue-router (для URL-sync). */
  routeName: string
  /** Параметры маршрута и props компонента (id, type). */
  params: Record<string, string | undefined>
  /** Есть несохранённые изменения (запрет закрытия без подтверждения). */
  dirty: boolean
  /** Можно ли закрыть таб. */
  closable: boolean
  /** Признак «нового» документа (замещается реальным id после сохранения). */
  transient: boolean
}

interface PersistedTab {
  id: string
  kind: DocumentKind
  title: string
  routeName: string
  params: Record<string, string | undefined>
  closable: boolean
}

const STORAGE_KEY = 'ctm.workspace.tabs.v1'
const ACTIVE_KEY = 'ctm.workspace.activeId.v1'

const REFERENCE_TITLES: Record<string, string> = {
  counterparties: 'Контрагенты',
  objects: 'Объекты',
  works: 'Работы',
  persons: 'Физлица',
  organizations: 'Организации',
  contracts: 'Договоры',
  warehouses: 'Склады',
  'material-packages': 'Упаковки товаров',
  'material-characteristics': 'Характеристики товаров',
  'material-series': 'Серии товаров',
}

/** Карта route name -> метаданные таба. */
interface RouteSpec {
  kind: DocumentKind
  title: string
  routeName: string
  closable: boolean
  transient?: boolean
}

function specFromRoute(route: RouteLocationNormalizedLoaded): RouteSpec | null {
  const name = route.name as string | null
  const params = route.params as Record<string, string | undefined>
  switch (name) {
    case 'sale-list':
      return { kind: 'sale-list', title: 'Продажи', routeName: 'sale-list', closable: true }
    case 'sale-create':
      return { kind: 'sale-form', title: 'Новый документ продажи', routeName: 'sale-create', closable: true, transient: true }
    case 'sale-edit':
      return { kind: 'sale-form', title: `Продажа №${params.id ?? ''}`, routeName: 'sale-edit', closable: true }
    case 'purchase-list':
      return { kind: 'purchase-list', title: 'Закупки', routeName: 'purchase-list', closable: true }
    case 'purchase-create':
      return { kind: 'purchase-form', title: 'Новый закупочный документ', routeName: 'purchase-create', closable: true, transient: true }
    case 'purchase-edit':
      return { kind: 'purchase-form', title: `Закупка №${params.id ?? ''}`, routeName: 'purchase-edit', closable: true }
    case 'dashboard':
      return { kind: 'dashboard', title: 'Обзор', routeName: 'dashboard', closable: true }
    case 'estimate-list':
      return { kind: 'estimate-list', title: 'Сметы', routeName: 'estimate-list', closable: true }
    case 'estimate-create':
      return { kind: 'estimate-form', title: 'Новая смета', routeName: 'estimate-create', closable: true, transient: true }
    case 'estimate-edit':
      return { kind: 'estimate-form', title: `Смета №${params.id ?? ''}`, routeName: 'estimate-edit', closable: true }
    case 'daily-report-list':
      return { kind: 'daily-report-list', title: 'Отчёты прораба', routeName: 'daily-report-list', closable: true }
    case 'daily-report-create':
      return { kind: 'daily-report-form', title: 'Новый отчёт', routeName: 'daily-report-create', closable: true, transient: true }
    case 'daily-report-edit':
      return { kind: 'daily-report-form', title: `Отчёт №${params.id ?? ''}`, routeName: 'daily-report-edit', closable: true }
    case 'timesheet-list':
      return { kind: 'timesheet-list', title: 'Табели', routeName: 'timesheet-list', closable: true }
    case 'timesheet-create':
      return { kind: 'timesheet-form', title: 'Новый табель', routeName: 'timesheet-create', closable: true, transient: true }
    case 'timesheet-edit':
      return { kind: 'timesheet-form', title: `Табель №${params.id ?? ''}`, routeName: 'timesheet-edit', closable: true }
    case 'work-execution-register':
      return { kind: 'work-execution-register', title: 'Регистр работ', routeName: 'work-execution-register', closable: true }
    case 'inventory-balances-report':
      return { kind: 'inventory-balances-report', title: 'Остатки ТМЦ', routeName: 'inventory-balances-report', closable: true }
    case 'settlements-turnover-report':
      return { kind: 'settlements-turnover-report', title: 'Оборотно-сальдовая ведомость', routeName: 'settlements-turnover-report', closable: true }
    case 'overdue-report':
      return { kind: 'overdue-report', title: 'Просроченная задолженность', routeName: 'overdue-report', closable: true }
    case 'import-profiles':
      return { kind: 'import-profiles', title: 'Профили импорта Excel', routeName: 'import-profiles', closable: true }
    case 'payment-schedule-list':
      return { kind: 'payment-schedule-list', title: 'Платёжные календари', routeName: 'payment-schedule-list', closable: true }
    case 'payment-schedule-create':
      return { kind: 'payment-schedule-form', title: 'Новый календарь', routeName: 'payment-schedule-create', closable: true, transient: true }
    case 'payment-schedule-edit':
      return { kind: 'payment-schedule-form', title: `Календарь №${params.id ?? ''}`, routeName: 'payment-schedule-edit', closable: true }
    case 'payment-calendar':
      return { kind: 'payment-calendar', title: 'Платёжный календарь', routeName: 'payment-calendar', closable: true }
    case 'payment-transaction-list':
      return { kind: 'payment-transaction-list', title: 'Платежи', routeName: 'payment-transaction-list', closable: true }
    case 'goods-receipt-list':
      return { kind: 'goods-receipt-list', title: 'Поступления ТМЦ', routeName: 'goods-receipt-list', closable: true }
    case 'goods-receipt-create':
      return { kind: 'goods-receipt-form', title: 'Новое поступление ТМЦ', routeName: 'goods-receipt-create', closable: true, transient: true }
    case 'goods-receipt-edit':
      return { kind: 'goods-receipt-form', title: `Поступление №${params.id ?? ''}`, routeName: 'goods-receipt-edit', closable: true }
    case 'goods-issue-list':
      return { kind: 'goods-issue-list', title: 'Списания ТМЦ', routeName: 'goods-issue-list', closable: true }
    case 'goods-issue-create':
      return { kind: 'goods-issue-form', title: 'Новое списание ТМЦ', routeName: 'goods-issue-create', closable: true, transient: true }
    case 'goods-issue-edit':
      return { kind: 'goods-issue-form', title: `Списание №${params.id ?? ''}`, routeName: 'goods-issue-edit', closable: true }
    case 'goods-price-adjustment-list':
      return { kind: 'goods-price-adjustment-list', title: 'Корректировки цен', routeName: 'goods-price-adjustment-list', closable: true }
    case 'opening-balance-list':
      return { kind: 'opening-balance-list', title: 'Начальные остатки', routeName: 'opening-balance-list', closable: true }
    case 'opening-balance-create':
      return { kind: 'opening-balance-form', title: 'Новые начальные остатки', routeName: 'opening-balance-create', closable: true, transient: true }
    case 'opening-balance-edit':
      return { kind: 'opening-balance-form', title: `Начальные остатки №${params.id ?? ''}`, routeName: 'opening-balance-edit', closable: true }
    case 'inventory-turnover-report':
      return { kind: 'inventory-turnover-report', title: 'Обороты ТМЦ', routeName: 'inventory-turnover-report', closable: true }
    case 'goods-price-adjustment-create':
      return { kind: 'goods-price-adjustment-form', title: 'Новая корректировка цены', routeName: 'goods-price-adjustment-create', closable: true, transient: true }
    case 'goods-price-adjustment-edit':
      return { kind: 'goods-price-adjustment-form', title: `Корректировка №${params.id ?? ''}`, routeName: 'goods-price-adjustment-edit', closable: true }
    case 'goods-return-list':
      return { kind: 'goods-return-list', title: 'Возвраты товаров', routeName: 'goods-return-list', closable: true }
    case 'goods-return-create':
      return { kind: 'goods-return-form', title: 'Новый возврат', routeName: 'goods-return-create', closable: true, transient: true }
    case 'goods-return-edit':
      return { kind: 'goods-return-form', title: `Возврат №${params.id ?? ''}`, routeName: 'goods-return-edit', closable: true }
    case 'goods-transfer-list':
      return { kind: 'goods-transfer-list', title: 'Перемещения ТМЦ', routeName: 'goods-transfer-list', closable: true }
    case 'goods-transfer-create':
      return { kind: 'goods-transfer-form', title: 'Новое перемещение ТМЦ', routeName: 'goods-transfer-create', closable: true, transient: true }
    case 'goods-transfer-edit':
      return { kind: 'goods-transfer-form', title: `Перемещение №${params.id ?? ''}`, routeName: 'goods-transfer-edit', closable: true }
    // Cost accounting — material consumptions
    case 'material-consumption-list':
      return { kind: 'material-consumption-list', title: 'Расход материалов', routeName: 'material-consumption-list', closable: true }
    case 'material-consumption-create':
      return { kind: 'material-consumption-form', title: 'Новый расход материалов', routeName: 'material-consumption-create', closable: true, transient: true }
    case 'material-consumption-edit':
      return { kind: 'material-consumption-form', title: `Расход материалов №${params.id ?? ''}`, routeName: 'material-consumption-edit', closable: true }
    // Cost accounting — machinery usage
    case 'machinery-usage-list':
      return { kind: 'machinery-usage-list', title: 'Рапорты машин', routeName: 'machinery-usage-list', closable: true }
    case 'machinery-usage-create':
      return { kind: 'machinery-usage-form', title: 'Новый рапорт машин', routeName: 'machinery-usage-create', closable: true, transient: true }
    case 'machinery-usage-edit':
      return { kind: 'machinery-usage-form', title: `Рапорт машин №${params.id ?? ''}`, routeName: 'machinery-usage-edit', closable: true }
    // Cost accounting — subcontract acceptances
    case 'subcontract-acceptance-list':
      return { kind: 'subcontract-acceptance-list', title: 'Акты субподряда', routeName: 'subcontract-acceptance-list', closable: true }
    case 'subcontract-acceptance-create':
      return { kind: 'subcontract-acceptance-form', title: 'Новый акт субподряда', routeName: 'subcontract-acceptance-create', closable: true, transient: true }
    case 'subcontract-acceptance-edit':
      return { kind: 'subcontract-acceptance-form', title: `Акт субподряда №${params.id ?? ''}`, routeName: 'subcontract-acceptance-edit', closable: true }
    // Cost accounting — overhead expenses
    case 'overhead-expense-list':
      return { kind: 'overhead-expense-list', title: 'Накладные расходы', routeName: 'overhead-expense-list', closable: true }
    case 'overhead-expense-create':
      return { kind: 'overhead-expense-form', title: 'Новые накладные расходы', routeName: 'overhead-expense-create', closable: true, transient: true }
    case 'overhead-expense-edit':
      return { kind: 'overhead-expense-form', title: `Накладные расходы №${params.id ?? ''}`, routeName: 'overhead-expense-edit', closable: true }
    // Cost accounting — cost calculations
    case 'cost-calculation-list':
      return { kind: 'cost-calculation-list', title: 'Расчёт себестоимости', routeName: 'cost-calculation-list', closable: true }
    case 'cost-calculation-create':
      return { kind: 'cost-calculation-form', title: 'Новый расчёт себестоимости', routeName: 'cost-calculation-create', closable: true, transient: true }
    case 'cost-calculation-edit':
      return { kind: 'cost-calculation-form', title: `Расчёт себестоимости №${params.id ?? ''}`, routeName: 'cost-calculation-edit', closable: true }
    // Cost accounting — reports
    case 'cost-card-report':
      return { kind: 'cost-card-report', title: 'Карточка себестоимости', routeName: 'cost-card-report', closable: true }
    case 'cost-turnover-report':
      return { kind: 'cost-turnover-report', title: 'Оборотка по затратам', routeName: 'cost-turnover-report', closable: true }
    case 'cost-deviations-report':
      return { kind: 'cost-deviations-report', title: 'Отклонения', routeName: 'cost-deviations-report', closable: true }
    case 'cost-profitability-report':
      return { kind: 'cost-profitability-report', title: 'Рентабельность', routeName: 'cost-profitability-report', closable: true }
    case 'sync':
      return { kind: 'sync', title: 'Синхронизация', routeName: 'sync', closable: true }
    case 'user-access':
      return { kind: 'user-access', title: 'Пользователи и доступ', routeName: 'user-access', closable: true }
    case 'work-list':
      return { kind: 'work-catalog', title: 'Работы (справочник)', routeName: 'work-list', closable: true }
    case 'reference-list': {
      const type = params.type ?? 'counterparties'
      return {
        kind: 'reference-list',
        title: REFERENCE_TITLES[type] ?? 'Справочник',
        routeName: 'reference-list',
        closable: true,
      }
    }
    default:
      return null
  }
}

/** Идентификатор таба по маршруту (для дедупликации). */
export function tabIdFromRoute(route: RouteLocationNormalizedLoaded): string | null {
  const spec = specFromRoute(route)
  if (!spec) return null
  const params = route.params as Record<string, string | undefined>
  switch (spec.kind) {
    case 'sale-list':
      return `sale-list:${params.saleKind}`
    case 'sale-form':
      return `sale-form:${params.saleKind}:${spec.transient ? 'new' : params.id}`
    case 'purchase-list':
      return `purchase-list:${params.purchaseKind}`
    case 'purchase-form':
      return `purchase-form:${params.purchaseKind}:${spec.transient ? 'new' : params.id}`
    case 'estimate-form':
    case 'daily-report-form':
    case 'timesheet-form':
    case 'payment-schedule-form':
    case 'goods-receipt-form':
    case 'goods-issue-form':
    case 'goods-price-adjustment-form':
    case 'opening-balance-form':
    case 'goods-return-form':
    case 'goods-transfer-form':
    case 'material-consumption-form':
    case 'machinery-usage-form':
    case 'subcontract-acceptance-form':
    case 'overhead-expense-form':
    case 'cost-calculation-form':
      return `${spec.kind}:${spec.transient ? 'new' : (params.id ?? 'new')}`
    case 'reference-list':
      return `${spec.kind}:${params.type ?? 'counterparties'}`
    default:
      return spec.kind
  }
}

interface WorkspaceState {
  tabs: WorkspaceTab[]
  activeId: string | null
  /** Счётчик для уникальных id дубликатов. */
  seq: number
  /** Запрошенная навигация; компонент-обёртка пушит её в роутер и сбрасывает. */
  pendingNavigation: NavigationTarget | null
}

function readPersisted(): { tabs: PersistedTab[]; activeId: string | null } | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedTab[]
    if (!Array.isArray(parsed)) return null
    const activeId = window.localStorage.getItem(ACTIVE_KEY)
    return { tabs: parsed, activeId }
  } catch {
    return null
  }
}

function routeToTab(route: RouteLocationNormalizedLoaded, id: string): WorkspaceTab | null {
  const spec = specFromRoute(route)
  if (!spec) return null
  const params = { ...(route.params as Record<string, string | undefined>) }
  return {
    id,
    kind: spec.kind,
    title: spec.title,
    routeName: spec.routeName,
    params,
    dirty: false,
    closable: spec.closable,
    transient: Boolean(spec.transient),
  }
}

export const useWorkspaceStore = defineStore('workspace', {
  state: (): WorkspaceState => {
    const persisted = readPersisted()
    if (persisted && persisted.tabs.length > 0) {
      const tabs: WorkspaceTab[] = persisted.tabs.map((t) => ({
        ...t,
        dirty: false,
        transient: t.id.endsWith(':new'),
      }))
      return {
        tabs,
        activeId: persisted.activeId && tabs.some((t) => t.id === persisted.activeId) ? persisted.activeId : tabs[0]?.id ?? null,
        seq: 0,
        pendingNavigation: null,
      }
    }
    return { tabs: [], activeId: null, seq: 0, pendingNavigation: null }
  },
  getters: {
    activeTab: (state) => state.tabs.find((t) => t.id === state.activeId) ?? null,
    hasDirty: (state) => state.tabs.some((t) => t.dirty),
    count: (state) => state.tabs.length,
  },
  actions: {
    /**
     * Синхронизирует состояние табов с текущим маршрутом.
     * Вызывается из router.afterEach. Идемпотентна.
     *
     * Возвращает true, если был создан/активирован таб (маршрут рабочий).
     */
    syncFromRoute(route: RouteLocationNormalizedLoaded): boolean {
      const spec = specFromRoute(route)
      if (!spec) return false

      const candidateId = tabIdFromRoute(route)
      if (!candidateId) return false

      const params = { ...(route.params as Record<string, string | undefined>) }

      // Сценарий «новая -> сохранённая»: активный transient-таб того же типа
      // замещается реальным идентификатором документа.
      const active = this.activeTab
      if (
        active &&
        active.transient &&
        active.kind === spec.kind &&
        (spec.kind !== 'purchase-form' || active.params.purchaseKind === params.purchaseKind) &&
        (spec.kind !== 'sale-form' || active.params.saleKind === params.saleKind) &&
        !spec.transient
      ) {
        const idx = this.tabs.findIndex((t) => t.id === active.id)
        if (idx >= 0) {
          this.tabs[idx] = {
            ...this.tabs[idx],
            id: candidateId,
            routeName: spec.routeName,
            title: spec.title,
            params,
            transient: false,
          }
          this.activeId = candidateId
          this.persist()
          return true
        }
      }

      // Дедуп: точное совпадение id.
      const exact = this.tabs.find((t) => t.id === candidateId)
      if (exact) {
        if (this.activeId !== exact.id) {
          this.activeId = exact.id
          this.persist()
        }
        return true
      }

      // Для singleton-видов (списки, регистр, дашборд, справочники по типу):
      // если уже открыт таб того же вида — активируем его (без дублирования).
      const singletonKinds: DocumentKind[] = [
        'dashboard',
        'estimate-list',
        'daily-report-list',
        'timesheet-list',
        'work-execution-register',
        'inventory-balances-report',
        'settlements-turnover-report',
        'overdue-report',
        'import-profiles',
        'goods-receipt-list',
        'goods-issue-list',
        'goods-price-adjustment-list',
        'opening-balance-list',
        'inventory-turnover-report',
        'goods-return-list',
        'goods-transfer-list',
        'material-consumption-list',
        'machinery-usage-list',
        'subcontract-acceptance-list',
        'overhead-expense-list',
        'cost-calculation-list',
        'cost-card-report',
        'cost-turnover-report',
        'cost-deviations-report',
        'cost-profitability-report',
        'reference-list',
        'work-catalog',
        'sync',
        'user-access',
      ]
      if (singletonKinds.includes(spec.kind)) {
        const sameKind = this.tabs.find((t) => t.kind === spec.kind && t.id === candidateId)
        if (sameKind) {
          this.activeId = sameKind.id
          this.persist()
          return true
        }
      }

      // Иначе создаём новый таб.
      const tab = routeToTab(route, candidateId)
      if (!tab) return false
      this.tabs.push(tab)
      this.activeId = tab.id
      this.persist()
      return true
    },

    /** Активирует таб по id и (опционально) запрашивает навигацию в URL. */
    select(id: string, push = true): void {
      const tab = this.tabs.find((t) => t.id === id)
      if (!tab) return
      if (this.activeId !== id) {
        this.activeId = id
        this.persist()
      }
      if (push) {
        this.requestNavigation(tab)
      }
    },

    /**
     * Закрывает таб. Если он «грязный» — вернёт false и не закроет
     * (вызывающий код должен подтвердить действие, затем force=true).
     */
    close(id: string, force = false): boolean {
      const idx = this.tabs.findIndex((t) => t.id === id)
      if (idx < 0) return true
      const tab = this.tabs[idx]
      if (tab.dirty && !force) {
        return false
      }
      const wasActive = this.activeId === id
      this.tabs.splice(idx, 1)
      if (wasActive) {
        const next = this.tabs[Math.min(idx, this.tabs.length - 1)] ?? null
        if (next) {
          this.activeId = next.id
          this.requestNavigation(next)
        } else {
          // Нет табов — открываем обзор как fallback.
          this.activeId = null
          this.openDashboard()
        }
      }
      this.persist()
      return true
    },

    closeOthers(id: string, force = false): boolean {
      const keep = this.tabs.find((t) => t.id === id)
      if (!keep) return true
      const dirtyOthers = this.tabs.filter((t) => t.id !== id && t.dirty)
      if (dirtyOthers.length > 0 && !force) {
        return false
      }
      this.tabs = [keep]
      this.activeId = id
      this.requestNavigation(keep)
      this.persist()
      return true
    },

    closeAll(force = false): boolean {
      if (this.tabs.some((t) => t.dirty) && !force) {
        return false
      }
      this.tabs = []
      this.activeId = null
      this.openDashboard()
      this.persist()
      return true
    },

    /** Дублирует таб (для мультитабов одного типа с разными фильтрами). */
    duplicate(id: string): void {
      const src = this.tabs.find((t) => t.id === id)
      if (!src) return
      this.seq += 1
      const clone: WorkspaceTab = {
        ...src,
        id: `${src.kind}#${this.seq}`,
        title: src.title,
        params: { ...src.params },
        dirty: false,
        transient: false,
      }
      this.tabs.push(clone)
      this.activeId = clone.id
      // URL не различает дубликаты — запрашиваем общий маршрут.
      this.requestNavigation(clone)
      this.persist()
    },

    rename(id: string, title: string): void {
      const tab = this.tabs.find((t) => t.id === id)
      if (!tab) return
      tab.title = title
      this.persist()
    },

    markDirty(id: string, dirty: boolean): void {
      const tab = this.tabs.find((t) => t.id === id)
      if (!tab || tab.dirty === dirty) return
      tab.dirty = dirty
      // dirty не персистируем — это runtime-флаг.
    },

    /** Привязывает активный таб к редактируемому документу после сохранения. */
    attachSaved(id: string, entityId: string, routeName: string, title: string): void {
      const idx = this.tabs.findIndex((t) => t.id === id)
      if (idx < 0) return
      const newId = `${this.tabs[idx].kind}:${entityId}`
      // Не создаём дубликат, если такой уже открыт.
      if (this.tabs.some((t, i) => i !== idx && t.id === newId)) {
        this.tabs.splice(idx, 1)
        this.activeId = newId
        this.persist()
        return
      }
      this.tabs[idx] = {
        ...this.tabs[idx],
        id: newId,
        params: { ...this.tabs[idx].params, id: entityId },
        routeName,
        title,
        transient: false,
        dirty: false,
      }
      this.activeId = newId
      this.persist()
    },

    /** Открывает/активирует обзор. Используется как fallback. */
    openDashboard(): void {
      const existing = this.tabs.find((t) => t.kind === 'dashboard')
      if (existing) {
        this.activeId = existing.id
      } else {
        const tab: WorkspaceTab = {
          id: 'dashboard',
          kind: 'dashboard',
          title: 'Обзор',
          routeName: 'dashboard',
          params: {},
          dirty: false,
          closable: true,
          transient: false,
        }
        this.tabs.push(tab)
        this.activeId = tab.id
      }
      this.requestNavigation(this.activeTab!)
      this.persist()
    },

    persist(): void {
      if (typeof window === 'undefined') return
      const persistable: PersistedTab[] = this.tabs.map((t) => ({
        id: t.id,
        kind: t.kind,
        title: t.title,
        routeName: t.routeName,
        params: t.params,
        closable: t.closable,
      }))
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(persistable))
        window.localStorage.setItem(ACTIVE_KEY, this.activeId ?? '')
      } catch {
        // ignore quota errors
      }
    },

    reset(): void {
      this.tabs = []
      this.activeId = null
      this.seq = 0
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(STORAGE_KEY)
        window.localStorage.removeItem(ACTIVE_KEY)
      }
    },

    /** Запрашивает навигацию к маршруту таба (обрабатывается компонентом-обёрткой). */
    requestNavigation(tab: WorkspaceTab | null): void {
      if (!tab) return
      this.pendingNavigation = {
        name: tab.routeName,
        params: { ...tab.params },
      }
    },

    /** Сбрасывает запрос навигации после обработки. */
    consumeNavigation(): NavigationTarget | null {
      const target = this.pendingNavigation
      this.pendingNavigation = null
      return target
    },
  },
})
