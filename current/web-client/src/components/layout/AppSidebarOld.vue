<template>
  <aside :class="['sidebar', 'panel', { open, compact, hidden: !open }]" aria-label="Навигационное меню">
    <div v-if="pinnedItems.length" class="menu-block">
      <div class="menu-block-title">Закреплено</div>
      <div class="menu-list">
        <RouterLink v-for="item in pinnedItems" :key="`pinned-${item.id}`" :to="item.to" custom v-slot="{ href, navigate, isActive }">
          <div :class="['menu-row', { active: isActive }]">
            <a :href="href" class="menu-link" @click="handleNavigate(navigate, $event)">
              <span class="menu-link-text">{{ item.label }}</span>
            </a>
            <button
              type="button"
              :class="['pin-button', { pinned: isPinned(item.id) }]"
              :aria-pressed="isPinned(item.id)"
              :title="isPinned(item.id) ? 'Убрать из закрепленных' : 'Закрепить сверху'"
              @click="togglePin(item.id)"
            >
              pin
            </button>
          </div>
        </RouterLink>
      </div>
    </div>

    <div v-for="section in visibleSections" :key="section.id" class="menu-block">
      <div class="menu-block-title">{{ section.label }}</div>
      <div class="menu-list">
        <RouterLink v-for="item in section.items" :key="item.id" :to="item.to" custom v-slot="{ href, navigate, isActive }">
          <div :class="['menu-row', { active: isActive }]">
            <a :href="href" class="menu-link" @click="handleNavigate(navigate, $event)">
              <span class="menu-link-text">{{ item.label }}</span>
            </a>
            <button
              type="button"
              :class="['pin-button', { pinned: isPinned(item.id) }]"
              :aria-pressed="isPinned(item.id)"
              :title="isPinned(item.id) ? 'Убрать из закрепленных' : 'Закрепить сверху'"
              @click="togglePin(item.id)"
            >
              pin
            </button>
          </div>
        </RouterLink>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type NavSectionId = 'documents' | 'reports' | 'references'

interface NavItem {
  id: string
  to: string
  label: string
  description: string
  section: NavSectionId
}

defineProps<{
  open: boolean
  compact?: boolean
}>()

const emit = defineEmits<{
  navigate: []
}>()

const PIN_STORAGE_KEY = 'ctm.sidebar.pins'
const DEFAULT_PINNED_IDS = ['dashboard']

const sections = [
  { id: 'documents' as const, label: 'Документы' },
  { id: 'reports' as const, label: 'Отчеты' },
  { id: 'references' as const, label: 'Справочники' },
]

const items: NavItem[] = [
  { id: 'opening-balance-list', to: '/goods/opening-balances', label: 'Начальные остатки', description: 'Склад и задолженность на дату начала', section: 'documents' },
  { id: 'inventory-turnover-report', to: '/reports/inventory-turnover', label: 'Обороты ТМЦ', description: 'Входящие остатки и обороты склада', section: 'reports' },
  { id: 'reference-material-packages', to: '/references/material-packages', label: 'Упаковки товаров', description: 'Пересчет в базовую единицу', section: 'references' },
  { id: 'reference-material-characteristics', to: '/references/material-characteristics', label: 'Характеристики товаров', description: 'Складские характеристики', section: 'references' },
  { id: 'reference-material-series', to: '/references/material-series', label: 'Серии товаров', description: 'Изоляция серий', section: 'references' },
  { id: 'dashboard', to: '/', label: 'Обзор', description: 'Документы и показатели', section: 'reports' },
  { id: 'estimate-list', to: '/documents/estimates', label: 'Сметы', description: 'Планирование и проведение', section: 'documents' },
  { id: 'daily-report-list', to: '/documents/daily-reports', label: 'Отчёты прораба', description: 'Фактические трудозатраты', section: 'documents' },
  { id: 'timesheet-list', to: '/documents/timesheets', label: 'Табели', description: 'Помесячный учет рабочего времени', section: 'documents' },
  { id: 'material-consumption-list', to: '/documents/material-consumptions', label: 'Расход материалов', description: 'Списание материалов на работы', section: 'documents' },
  { id: 'machinery-usage-list', to: '/documents/machinery-usage', label: 'Рапорты машин', description: 'Учет работы машин и механизмов', section: 'documents' },
  { id: 'subcontract-acceptance-list', to: '/documents/subcontract-acceptances', label: 'Акты субподряда', description: 'Приемка субподрядных работ', section: 'documents' },
  { id: 'overhead-expense-list', to: '/documents/overhead-expenses', label: 'Накладные расходы', description: 'Косвенные расходы периода', section: 'documents' },
  { id: 'cost-calculation-list', to: '/documents/cost-calculations', label: 'Расчёт себестоимости', description: 'Закрытие периода и фин. результат', section: 'documents' },
  { id: 'payment-schedule-list', to: '/payments/schedules', label: 'Календари платежей', description: 'Планирование поступлений и платежей', section: 'documents' },
  { id: 'payment-transaction-list', to: '/payments/transactions', label: 'Платежи (факт)', description: 'Фактические движения денег', section: 'documents' },
  { id: 'goods-receipt-list', to: '/goods/receipts', label: 'Поступления ТМЦ', description: 'Приёмка материалов, кредиторская задолженность', section: 'documents' },
  { id: 'purchase-list', to: '/purchases/orders', label: 'Закупки', description: 'Заказы, приемка, приобретения и расхождения', section: 'documents' },
  { id: 'sale-list', to: '/sales/orders', label: 'Продажи', description: 'Заказы, резервирование, реализация и отгрузка', section: 'documents' },
  { id: 'goods-issue-list', to: '/goods/issues', label: 'Списания ТМЦ', description: 'Отгрузка/списание в производство, дебиторка', section: 'documents' },
  { id: 'goods-price-adjustment-list', to: '/goods/price-adjustments', label: 'Корректировки цен', description: 'Цены продажи и закупки', section: 'documents' },
  { id: 'goods-return-list', to: '/goods/returns', label: 'Возвраты товаров', description: 'Возвраты и возврат денег', section: 'documents' },
  { id: 'goods-transfer-list', to: '/goods/transfers', label: 'Перемещения ТМЦ', description: 'Перемещения между складами', section: 'documents' },
  { id: 'work-execution-register', to: '/registers/work-execution', label: 'Регистр работ', description: 'Движения по объектам и сметам', section: 'reports' },
  { id: 'cost-card-report', to: '/reports/cost-card', label: 'Карточка себестоимости', description: 'План-факт анализ по объекту', section: 'reports' },
  { id: 'cost-turnover-report', to: '/reports/cost-turnover', label: 'Оборотка по затратам', description: 'Оборотно-сальдовая ведомость', section: 'reports' },
  { id: 'cost-deviations-report', to: '/reports/cost-deviations', label: 'Отклонения', description: 'Превышение факта над планом', section: 'reports' },
  { id: 'cost-profitability-report', to: '/reports/cost-profitability', label: 'Рентабельность', description: 'Прибыль и рентабельность объектов', section: 'reports' },
  { id: 'inventory-balances-report', to: '/reports/inventory-balances', label: 'Остатки ТМЦ', description: 'Складские остатки на дату', section: 'reports' },
  { id: 'settlements-turnover-report', to: '/reports/settlements-turnover', label: 'Оборотно-сальдовая ведомость', description: 'Взаиморасчеты: сальдо и обороты', section: 'reports' },
  { id: 'overdue-report', to: '/reports/overdue', label: 'Просроченная задолженность', description: 'Дебиторская и кредиторская просрочка', section: 'reports' },
  { id: 'payment-calendar', to: '/payments/calendar', label: 'Платёжный календарь', description: 'План/факт денежных потоков', section: 'reports' },
  { id: 'reference-counterparties', to: '/references/counterparties', label: 'Контрагенты', description: 'Заказчики и владельцы объектов', section: 'references' },
  { id: 'reference-objects', to: '/references/objects', label: 'Объекты', description: 'Строительные площадки и адреса', section: 'references' },
  { id: 'reference-works', to: '/references/works', label: 'Работы', description: 'Нормы, цены и единицы измерения', section: 'references' },
  { id: 'reference-materials', to: '/references/materials', label: 'Материалы', description: 'Материалы, единицы и цены', section: 'references' },
  { id: 'reference-warehouses', to: '/references/warehouses', label: 'Склады', description: 'Места хранения ТМЦ', section: 'references' },
  { id: 'reference-persons', to: '/references/persons', label: 'Физлица', description: 'Сотрудники, исполнители, прорабы', section: 'references' },
  { id: 'reference-organizations', to: '/references/organizations', label: 'Организации', description: 'Подрядчики и структуры', section: 'references' },
  { id: 'reference-contracts', to: '/references/contracts', label: 'Договоры', description: 'Договоры и доп. соглашения', section: 'references' },
  { id: 'import-profiles', to: '/settings/import-profiles', label: 'Профили импорта', description: 'Шаблоны загрузки Excel для ТМЦ и спецификаций', section: 'references' },
  { id: 'sync', to: '/sync', label: 'Синхронизация', description: 'Обмен между базами', section: 'references' },
]

const itemMap = new Map(items.map((item) => [item.id, item]))
const pinnedIds = ref<string[]>([...DEFAULT_PINNED_IDS])

const pinnedIdSet = computed(() => new Set(pinnedIds.value))

const pinnedItems = computed(() =>
  pinnedIds.value.map((id) => itemMap.get(id)).filter((item): item is NavItem => Boolean(item)),
)

const visibleSections = computed(() =>
  sections
    .map((section) => ({
      ...section,
      items: items.filter((item) => item.section === section.id && !pinnedIdSet.value.has(item.id)),
    }))
    .filter((section) => section.items.length > 0),
)

onMounted(() => {
  if (typeof window === 'undefined') {
    return
  }

  const saved = window.localStorage.getItem(PIN_STORAGE_KEY)
  if (!saved) {
    pinnedIds.value = [...DEFAULT_PINNED_IDS]
    return
  }

  try {
    const parsed = JSON.parse(saved)
    if (!Array.isArray(parsed)) {
      pinnedIds.value = [...DEFAULT_PINNED_IDS]
      return
    }

    const nextIds = parsed.filter((id): id is string => typeof id === 'string' && itemMap.has(id))
    pinnedIds.value = nextIds
  } catch {
    pinnedIds.value = [...DEFAULT_PINNED_IDS]
  }
})

watch(
  pinnedIds,
  (value) => {
    if (typeof window === 'undefined') {
      return
    }

    window.localStorage.setItem(PIN_STORAGE_KEY, JSON.stringify(value))
  },
  { deep: true },
)

function isPinned(id: string) {
  return pinnedIdSet.value.has(id)
}

function togglePin(id: string) {
  if (!itemMap.has(id)) {
    return
  }

  if (isPinned(id)) {
    pinnedIds.value = pinnedIds.value.filter((currentId) => currentId !== id)
    return
  }

  pinnedIds.value = [...pinnedIds.value, id]
}

function handleNavigate(navigate: (event?: MouseEvent) => void, event: MouseEvent) {
  navigate(event)
  emit('navigate')
}
</script>

<style scoped>
.sidebar {
  position: fixed;
  top: 4.6rem;
  left: 0.9rem;
  z-index: 50;
  width: min(20rem, calc(100vw - 1.8rem));
  max-height: calc(100vh - 5.5rem);
  overflow: auto;
  padding: 0.7rem;
  border-radius: 22px;
  transform-origin: top left;
  transition:
    transform 150ms ease,
    opacity 150ms ease;
}

.sidebar.hidden {
  opacity: 0;
  transform: translateY(-0.35rem) scale(0.97);
  pointer-events: none;
}

.menu-block + .menu-block {
  margin-top: 0.7rem;
  padding-top: 0.65rem;
  border-top: 1px solid var(--border);
}

.menu-block-title {
  margin-bottom: 0.35rem;
  padding-inline: 0.3rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.menu-list {
  display: grid;
  gap: 0.28rem;
}

.menu-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.45rem;
  border-radius: 16px;
  padding: 0.18rem;
  transition: background-color 140ms ease;
}

.menu-row.active {
  background: var(--accent-ghost);
}

.menu-link {
  min-width: 0;
  padding: 0.55rem 0.7rem;
  border-radius: 14px;
}

.menu-link-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 700;
}

.pin-button {
  min-width: 2.75rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--text-soft);
  padding: 0.34rem 0.55rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  transition:
    background-color 140ms ease,
    color 140ms ease,
    border-color 140ms ease;
}

.pin-button.pinned {
  border-color: rgba(178, 76, 45, 0.32);
  background: var(--accent-ghost);
  color: var(--accent);
}

.sidebar.compact {
  top: 4rem;
  width: min(18rem, calc(100vw - 1.5rem));
  max-height: calc(100vh - 4.8rem);
  padding: 0.58rem;
}

.sidebar.compact .menu-block + .menu-block {
  margin-top: 0.55rem;
  padding-top: 0.55rem;
}

.sidebar.compact .menu-link {
  padding: 0.44rem 0.58rem;
}

.sidebar.compact .menu-link-text {
  font-size: 0.9rem;
}

.sidebar.compact .pin-button {
  min-width: 2.45rem;
  padding: 0.25rem 0.45rem;
  font-size: 0.66rem;
}

@media (max-width: 767px) {
  .sidebar {
    top: 4.9rem;
    left: 0.75rem;
    width: min(18rem, calc(100vw - 1.5rem));
    max-height: calc(100vh - 5.65rem);
  }
}
</style>
