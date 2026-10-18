<template>
  <aside :class="['sidebar', 'panel', { open, compact, hidden: !open }]" aria-label="Навигационное меню">
    <div v-for="section in sections" :key="section.id" class="menu-block">
      <!-- Section header: collapse/expand section + collapsed-items indicator -->
      <button
        type="button"
        class="menu-block-header"
        :aria-expanded="expandedSections.has(section.id)"
        @click="toggleSection(section.id)"
      >
        <span class="menu-block-arrow">{{ expandedSections.has(section.id) ? '▾' : '▸' }}</span>
        <span class="menu-block-title">{{ section.label }}</span>
        <span
          v-if="collapsedCount(section.id) > 0"
          class="collapsed-indicator"
          :class="{ open: collapsedZoneOpen.has(section.id) }"
          :title="collapsedZoneOpen.has(section.id) ? 'Скрыть свёрнутые' : `Показать свёрнутые (${collapsedCount(section.id)})`"
          @click.stop="toggleCollapsedZone(section.id)"
        >
          &raquo;&nbsp;{{ collapsedCount(section.id) }}
        </span>
      </button>

      <!-- Section body (collapsible) -->
      <div v-if="expandedSections.has(section.id)" class="menu-section-body">
        <!-- Normal (expanded) items -->
        <div v-if="normalItems(section.id).length > 0" class="menu-list">
          <div
            v-for="item in normalItems(section.id)"
            :key="item.id"
            :class="['menu-row', { active: isItemActive(item.to) }]"
          >
            <RouterLink :to="item.to" custom v-slot="{ href, navigate }">
              <a :href="href" class="menu-link" @click="handleNavigate(navigate, $event)">
                <span class="menu-link-icon" aria-hidden="true">{{ item.icon }}</span>
                <span class="menu-link-text">{{ item.label }}</span>
              </a>
            </RouterLink>
            <button
              type="button"
              class="collapse-button"
              :title="'Свернуть в компактный вид'"
              @click="collapseItem(item.id)"
            >
              &minus;
            </button>
          </div>
        </div>

        <!-- Collapsed zone (togglable via >> on header) -->
        <div v-if="collapsedItems(section.id).length > 0 && collapsedZoneOpen.has(section.id)" class="collapsed-zone">
          <div class="collapsed-zone-divider"></div>
          <div class="collapsed-zone-label">Свёрнуто</div>
          <div class="collapsed-chips">
            <div
              v-for="item in collapsedItems(section.id)"
              :key="item.id"
              class="collapsed-chip-wrapper"
              :title="item.label"
            >
              <RouterLink :to="item.to" custom v-slot="{ href, navigate }">
                <a
                  :href="href"
                  :class="['collapsed-chip', { active: isItemActive(item.to) }]"
                  @click="handleNavigate(navigate, $event)"
                >
                  <span class="collapsed-chip-icon" aria-hidden="true">{{ item.icon }}</span>
                  <span class="collapsed-chip-label">{{ item.shortLabel || item.label.charAt(0) }}</span>
                </a>
              </RouterLink>
              <button
                type="button"
                class="expand-chip-button"
                title="Развернуть в полный вид"
                @click="expandItem(item.id)"
              >
                +
              </button>
            </div>
          </div>
        </div>

        <!-- Empty section fallback -->
        <div
          v-if="normalItems(section.id).length === 0 && collapsedItems(section.id).length === 0"
          class="menu-empty"
        >
          Нет элементов
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

type NavSectionId = 'documents' | 'reports' | 'references'

interface NavItem {
  id: string
  to: string
  label: string
  shortLabel?: string
  description: string
  icon: string
  section: NavSectionId
  initiallyCollapsed?: boolean
}

defineProps<{
  open: boolean
  compact?: boolean
}>()

const emit = defineEmits<{
  navigate: []
}>()

const route = useRoute()

// -- Storage keys -----------------------------------------------------------
const COLLAPSED_ITEMS_KEY = 'ctm.sidebar.collapsed-items'
const COLLAPSED_ZONES_KEY = 'ctm.sidebar.collapsed-zones'
const EXPANDED_SECTIONS_KEY = 'ctm.sidebar.expanded-sections'

// -- Sections ---------------------------------------------------------------
const sections = [
  { id: 'documents' as const, label: 'Документы' },
  { id: 'reports' as const, label: 'Отчёты' },
  { id: 'references' as const, label: 'Справочники' },
]

// -- All navigation items ---------------------------------------------------
const items: NavItem[] = [
  {
    id: 'dashboard', to: '/', label: 'Обзор', shortLabel: 'Обз',
    description: 'Документы и показатели',
    icon: '⊡', section: 'reports',
  },
  {
    id: 'estimate-list', to: '/documents/estimates', label: 'Сметы', shortLabel: 'См',
    description: 'Планирование и проведение',
    icon: '▦', section: 'documents',
  },
  {
    id: 'daily-report-list', to: '/documents/daily-reports', label: 'Отчёты прораба', shortLabel: 'ОП',
    description: 'Фактические трудозатраты',
    icon: '◷', section: 'documents',
  },
  {
    id: 'timesheet-list', to: '/documents/timesheets', label: 'Табели', shortLabel: 'Таб',
    description: 'Помесячный учёт рабочего времени',
    icon: '◴', section: 'documents',
  },
  {
    id: 'material-consumption-list', to: '/documents/material-consumptions', label: 'Расход материалов', shortLabel: 'РМ',
    description: 'Списание материалов на работы',
    icon: '◆', section: 'documents',
  },
  {
    id: 'machinery-usage-list', to: '/documents/machinery-usage', label: 'Рапорты машин', shortLabel: 'Маш',
    description: 'Учёт работы машин и механизмов',
    icon: '⚙', section: 'documents',
  },
  {
    id: 'subcontract-acceptance-list', to: '/documents/subcontract-acceptances', label: 'Акты субподряда', shortLabel: 'Суб',
    description: 'Приёмка субподрядных работ',
    icon: '◈', section: 'documents',
  },
  {
    id: 'overhead-expense-list', to: '/documents/overhead-expenses', label: 'Накладные расходы', shortLabel: 'НР',
    description: 'Косвенные расходы периода',
    icon: '◎', section: 'documents',
    initiallyCollapsed: true,
  },
  {
    id: 'cost-calculation-list', to: '/documents/cost-calculations', label: 'Расчёт себестоимости', shortLabel: 'Сб',
    description: 'Закрытие периода и фин. результат',
    icon: '∑', section: 'documents',
  },
  {
    id: 'payment-schedule-list', to: '/payments/schedules', label: 'Календари платежей', shortLabel: 'КП',
    description: 'Планирование поступлений и платежей',
    icon: '▤', section: 'documents',
    initiallyCollapsed: true,
  },
  {
    id: 'payment-transaction-list', to: '/payments/transactions', label: 'Платежи (факт)', shortLabel: 'Пл',
    description: 'Фактические движения денег',
    icon: '⬡', section: 'documents',
    initiallyCollapsed: true,
  },
  {
    id: 'goods-receipt-list', to: '/goods/receipts', label: 'Поступления ТМЦ', shortLabel: 'ПТ',
    description: 'Приёмка материалов, кредиторская задолженность',
    icon: '▣', section: 'documents',
    initiallyCollapsed: true,
  },
  {
    id: 'goods-issue-list', to: '/goods/issues', label: 'Списания ТМЦ', shortLabel: 'СТ',
    description: 'Отгрузка/списание в производство, дебиторка',
    icon: '□', section: 'documents',
    initiallyCollapsed: true,
  },
  {
    id: 'goods-price-adjustment-list', to: '/goods/price-adjustments', label: 'Корректировки цен', shortLabel: 'КЦ',
    description: 'Изменение цен продажи и закупки', icon: '±', section: 'documents', initiallyCollapsed: true,
  },
  {
    id: 'goods-return-list', to: '/goods/returns', label: 'Возвраты товаров', shortLabel: 'ВТ',
    description: 'Возвраты клиентов и поставщикам, возврат денег', icon: '↩', section: 'documents',
    initiallyCollapsed: true,
  },
  {
    id: 'goods-transfer-list', to: '/goods/transfers', label: 'Перемещения ТМЦ', shortLabel: 'ПМ',
    description: 'Перемещения между складами', icon: '⇄', section: 'documents',
    initiallyCollapsed: true,
  },
  // Reports
  { id: 'purchase-list', to: '/purchases/orders', label: 'Закупки', shortLabel: 'Зк', description: 'Заказы, приемка, приобретения и расхождения', icon: '▣', section: 'documents' },
  { id: 'sale-list', to: '/sales/orders', label: 'Продажи', shortLabel: 'Пр', description: 'Заказы, резервирование, реализация и отгрузка', icon: '▣', section: 'documents' },
  { id: 'opening-balance-list', to: '/goods/opening-balances', label: 'Начальные остатки', shortLabel: 'НО', description: 'Товары и задолженность на дату начала', icon: '◷', section: 'documents' },
  { id: 'inventory-turnover-report', to: '/reports/inventory-turnover', label: 'Обороты ТМЦ', shortLabel: 'ОТ', description: 'Входящие остатки и обороты склада', icon: '▤', section: 'reports' },
  { id: 'reference-material-packages', to: '/references/material-packages', label: 'Упаковки товаров', shortLabel: 'Уп', description: 'Пересчет в базовую единицу', icon: '▣', section: 'references' },
  { id: 'reference-material-characteristics', to: '/references/material-characteristics', label: 'Характеристики товаров', shortLabel: 'Хр', description: 'Складские характеристики', icon: '◇', section: 'references' },
  { id: 'reference-material-series', to: '/references/material-series', label: 'Серии товаров', shortLabel: 'Ср', description: 'Изоляция серий на складе', icon: '#', section: 'references' },
  {
    id: 'work-execution-register', to: '/registers/work-execution', label: 'Регистр работ', shortLabel: 'РР',
    description: 'Движения по объектам и сметам',
    icon: '≡', section: 'reports',
  },
  {
    id: 'cost-card-report', to: '/reports/cost-card', label: 'Карточка себестоимости', shortLabel: 'КС',
    description: 'План-факт анализ по объекту',
    icon: '◉', section: 'reports',
  },
  {
    id: 'cost-turnover-report', to: '/reports/cost-turnover', label: 'Оборотка по затратам', shortLabel: 'ОЗ',
    description: 'Оборотно-сальдовая ведомость',
    icon: '⥁', section: 'reports',
  },
  {
    id: 'cost-deviations-report', to: '/reports/cost-deviations', label: 'Отклонения', shortLabel: 'Отк',
    description: 'Превышение факта над планом',
    icon: '⚡', section: 'reports',
    initiallyCollapsed: true,
  },
  {
    id: 'cost-profitability-report', to: '/reports/cost-profitability', label: 'Рентабельность', shortLabel: 'Рен',
    description: 'Прибыль и рентабельность объектов',
    icon: '↑', section: 'reports',
    initiallyCollapsed: true,
  },
  {
    id: 'inventory-balances-report', to: '/reports/inventory-balances', label: 'Остатки ТМЦ', shortLabel: 'Ост',
    description: 'Складские остатки на дату',
    icon: '◫', section: 'reports',
    initiallyCollapsed: true,
  },
  {
    id: 'settlements-turnover-report', to: '/reports/settlements-turnover', label: 'Оборотно-сальдовая ведомость', shortLabel: 'ОСВ',
    description: 'Взаиморасчёты: сальдо и обороты',
    icon: '⤄', section: 'reports',
    initiallyCollapsed: true,
  },
  {
    id: 'overdue-report', to: '/reports/overdue', label: 'Просроченная задолженность', shortLabel: 'ПЗ',
    description: 'Дебиторская и кредиторская просрочка',
    icon: '⏰', section: 'reports',
    initiallyCollapsed: true,
  },
  {
    id: 'payment-calendar', to: '/payments/calendar', label: 'Платёжный календарь', shortLabel: 'ПК',
    description: 'План/факт денежных потоков',
    icon: '▦', section: 'reports',
    initiallyCollapsed: true,
  },
  // References
  {
    id: 'reference-counterparties', to: '/references/counterparties', label: 'Контрагенты', shortLabel: 'Кн',
    description: 'Заказчики и владельцы объектов',
    icon: '⊙', section: 'references',
  },
  {
    id: 'reference-objects', to: '/references/objects', label: 'Объекты', shortLabel: 'Об',
    description: 'Строительные площадки и адреса',
    icon: '⌂', section: 'references',
  },
  {
    id: 'reference-works', to: '/references/works', label: 'Работы', shortLabel: 'Рб',
    description: 'Нормы, цены и единицы измерения',
    icon: '⚒', section: 'references',
  },
  {
    id: 'reference-materials', to: '/references/materials', label: 'Материалы', shortLabel: 'Мт',
    description: 'Материалы, единицы и цены',
    icon: '◇', section: 'references',
  },
  {
    id: 'reference-warehouses', to: '/references/warehouses', label: 'Склады', shortLabel: 'Ск',
    description: 'Места хранения ТМЦ', icon: '▣', section: 'references',
  },
  {
    id: 'reference-persons', to: '/references/persons', label: 'Физлица', shortLabel: 'ФЛ',
    description: 'Сотрудники, исполнители, прорабы',
    icon: '⊙', section: 'references',
    initiallyCollapsed: true,
  },
  {
    id: 'reference-organizations', to: '/references/organizations', label: 'Организации', shortLabel: 'Ор',
    description: 'Подрядчики и структуры',
    icon: '▥', section: 'references',
    initiallyCollapsed: true,
  },
  {
    id: 'reference-contracts', to: '/references/contracts', label: 'Договоры', shortLabel: 'Дг',
    description: 'Договоры и доп. соглашения',
    icon: '⚖', section: 'references',
  },
  {
    id: 'import-profiles', to: '/settings/import-profiles', label: 'Профили импорта', shortLabel: 'Им',
    description: 'Шаблоны загрузки Excel для ТМЦ и спецификаций',
    icon: '⇧', section: 'references',
    initiallyCollapsed: true,
  },
  {
    id: 'sync', to: '/sync', label: 'Синхронизация', shortLabel: 'Сн',
    description: 'Обмен между базами',
    icon: '⟳', section: 'references',
    initiallyCollapsed: true,
  },
]

// -- Derived maps -----------------------------------------------------------
const itemMap = new Map(items.map((item) => [item.id, item]))

// -- Reactive state ---------------------------------------------------------
const collapsedItemIds = ref<Set<string>>(new Set())
const collapsedZoneOpen = ref<Set<string>>(new Set(['documents', 'reports', 'references']))
const expandedSections = ref<Set<string>>(new Set(['documents', 'reports', 'references']))

// -- Initial collapsed items (from item defs) -------------------------------
const defaultCollapsedIds = new Set(
  items.filter((item) => item.initiallyCollapsed).map((item) => item.id),
)

// -- Persistence helpers ----------------------------------------------------
function loadSet(key: string, fallback: Set<string>): Set<string> {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    const arr: unknown = JSON.parse(raw)
    if (!Array.isArray(arr)) return fallback
    return new Set(arr.filter((v): v is string => typeof v === 'string'))
  } catch {
    return fallback
  }
}

function saveSet(key: string, value: Set<string>) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(key, JSON.stringify([...value]))
}

// -- Init -------------------------------------------------------------------
onMounted(() => {
  collapsedItemIds.value = loadSet(COLLAPSED_ITEMS_KEY, defaultCollapsedIds)
  collapsedZoneOpen.value = loadSet(COLLAPSED_ZONES_KEY, new Set(['documents', 'reports', 'references']))
  expandedSections.value = loadSet(EXPANDED_SECTIONS_KEY, new Set(['documents', 'reports', 'references']))
})

watch(collapsedItemIds, (v) => saveSet(COLLAPSED_ITEMS_KEY, v), { deep: true })
watch(collapsedZoneOpen, (v) => saveSet(COLLAPSED_ZONES_KEY, v), { deep: true })
watch(expandedSections, (v) => saveSet(EXPANDED_SECTIONS_KEY, v), { deep: true })

// -- Computed: items per section, split by collapsed state ------------------
function normalItems(sectionId: NavSectionId): NavItem[] {
  return items.filter(
    (item) => item.section === sectionId && !collapsedItemIds.value.has(item.id),
  )
}

function collapsedItems(sectionId: NavSectionId): NavItem[] {
  return items.filter(
    (item) => item.section === sectionId && collapsedItemIds.value.has(item.id),
  )
}

function collapsedCount(sectionId: NavSectionId): number {
  return collapsedItems(sectionId).length
}

// -- Active state via router ------------------------------------------------
function isItemActive(to: string): boolean {
  return route.path === to || (to !== '/' && route.path.startsWith(to))
}

// -- Actions ----------------------------------------------------------------
function toggleSection(sectionId: string) {
  const next = new Set(expandedSections.value)
  if (next.has(sectionId)) {
    next.delete(sectionId)
  } else {
    next.add(sectionId)
  }
  expandedSections.value = next
}

function toggleCollapsedZone(sectionId: string) {
  const next = new Set(collapsedZoneOpen.value)
  if (next.has(sectionId)) {
    next.delete(sectionId)
  } else {
    next.add(sectionId)
  }
  collapsedZoneOpen.value = next
}

function collapseItem(itemId: string) {
  const next = new Set(collapsedItemIds.value)
  next.add(itemId)
  collapsedItemIds.value = next
}

function expandItem(itemId: string) {
  const next = new Set(collapsedItemIds.value)
  next.delete(itemId)
  collapsedItemIds.value = next
}

function handleNavigate(navigate: (event?: MouseEvent) => void, event: MouseEvent) {
  navigate(event)
  emit('navigate')
}
</script>

<style scoped>
/* ---- Sidebar shell (matches original) ----------------------------------- */
.sidebar {
  position: fixed;
  top: 4.6rem;
  left: 0.9rem;
  z-index: 50;
  width: min(22rem, calc(100vw - 1.8rem));
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

/* ---- Section blocks ------------------------------------------------------ */
.menu-block + .menu-block {
  margin-top: 0.45rem;
  padding-top: 0.45rem;
  border-top: 1px solid var(--border);
}

/* ---- Section header (clickable row) ------------------------------------- */
.menu-block-header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0.45rem 0.35rem;
  border-radius: 14px;
  cursor: pointer;
  color: var(--text);
  transition: background-color 140ms ease;
  user-select: none;
}

.menu-block-header:hover {
  background: rgba(178, 76, 45, 0.06);
}

.menu-block-arrow {
  font-size: 0.72rem;
  color: var(--text-soft);
  width: 1rem;
  flex-shrink: 0;
  text-align: center;
  transition: transform 140ms ease;
}

.menu-block-title {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-soft);
  flex: 1;
  text-align: left;
}

/* ---- Collapsed indicator (>> N) on header ------------------------------- */
.collapsed-indicator {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text-soft);
  background: rgba(178, 76, 45, 0.07);
  border-radius: 999px;
  padding: 0.18rem 0.55rem;
  transition:
    background-color 140ms ease,
    color 140ms ease;
  letter-spacing: 0.03em;
  cursor: pointer;
}

.collapsed-indicator:hover {
  background: rgba(178, 76, 45, 0.15);
  color: var(--accent);
}

.collapsed-indicator.open {
  background: rgba(178, 76, 45, 0.12);
  color: var(--accent);
}

/* ---- Normal item rows ---------------------------------------------------- */
.menu-section-body {
  /* smooth expand */
}

.menu-list {
  display: grid;
  gap: 0.28rem;
}

.menu-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.35rem;
  border-radius: 16px;
  padding: 0.18rem;
  transition: background-color 140ms ease;
}

.menu-row.active {
  background: var(--accent-ghost);
}

.menu-link {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
  padding: 0.55rem 0.7rem;
  border-radius: 14px;
}

.menu-link-icon {
  flex-shrink: 0;
  width: 1.35rem;
  text-align: center;
  font-size: 1.05rem;
  color: var(--text-soft);
  font-family:
    'Segoe UI Symbol',
    'Noto Sans Symbols 2',
    sans-serif;
}

.menu-link-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 700;
}

/* ---- Collapse button (normal items) ------------------------------------- */
.collapse-button {
  min-width: 2.5rem;
  height: 2.2rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--text-soft);
  padding: 0;
  font-size: 1rem;
  font-weight: 700;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    background-color 140ms ease,
    color 140ms ease,
    border-color 140ms ease;
}

.collapse-button:hover {
  border-color: rgba(178, 76, 45, 0.28);
  background: var(--accent-ghost);
  color: var(--accent);
}

/* ---- Collapsed zone ------------------------------------------------------ */
.collapsed-zone-divider {
  margin: 0.45rem 0.35rem 0.35rem;
  border-top: 1px dashed var(--border);
}

.collapsed-zone-label {
  padding: 0.2rem 0.5rem 0.35rem;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-soft);
  opacity: 0.7;
}

.collapsed-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  padding: 0 0.2rem 0.2rem;
}

/* ---- Collapsed chip (icon + short label) -------------------------------- */
.collapsed-chip-wrapper {
  display: flex;
  align-items: stretch;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid var(--border);
  overflow: hidden;
  transition:
    border-color 140ms ease,
    box-shadow 140ms ease;
}

.collapsed-chip-wrapper:hover {
  border-color: rgba(178, 76, 45, 0.2);
  box-shadow: 0 4px 12px rgba(64, 49, 34, 0.06);
}

.collapsed-chip {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.42rem 0.55rem;
  text-decoration: none;
  color: var(--text);
  transition: background-color 140ms ease;
  border-radius: 11px 0 0 11px;
}

.collapsed-chip:hover {
  background: rgba(178, 76, 45, 0.05);
}

.collapsed-chip.active {
  background: var(--accent-ghost);
}

.collapsed-chip-icon {
  flex-shrink: 0;
  font-size: 1.05rem;
  width: 1.35rem;
  text-align: center;
  color: var(--text-soft);
  font-family:
    'Segoe UI Symbol',
    'Noto Sans Symbols 2',
    sans-serif;
}

.collapsed-chip-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-soft);
}

/* ---- Expand button (on collapsed chips) --------------------------------- */
.expand-chip-button {
  width: 1.8rem;
  border: 0;
  border-left: 1px solid var(--border);
  background: transparent;
  color: var(--text-soft);
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    background-color 140ms ease,
    color 140ms ease;
  border-radius: 0 11px 11px 0;
}

.expand-chip-button:hover {
  background: var(--accent-ghost);
  color: var(--accent);
}

/* ---- Empty state --------------------------------------------------------- */
.menu-empty {
  padding: 0.55rem 0.7rem;
  font-size: 0.78rem;
  color: var(--text-soft);
  font-style: italic;
  opacity: 0.6;
}

/* ---- Compact mode overrides --------------------------------------------- */
.sidebar.compact {
  top: 4rem;
  width: min(20rem, calc(100vw - 1.5rem));
  max-height: calc(100vh - 4.8rem);
  padding: 0.58rem;
}

.sidebar.compact .menu-block + .menu-block {
  margin-top: 0.35rem;
  padding-top: 0.35rem;
}

.sidebar.compact .menu-link {
  padding: 0.44rem 0.58rem;
}

.sidebar.compact .menu-link-text {
  font-size: 0.9rem;
}

.sidebar.compact .collapse-button {
  min-width: 2.2rem;
  height: 1.9rem;
  font-size: 0.85rem;
}

.sidebar.compact .collapsed-chip {
  padding: 0.35rem 0.45rem;
}

.sidebar.compact .collapsed-chip-label {
  font-size: 0.68rem;
}

.sidebar.compact .expand-chip-button {
  width: 1.6rem;
  font-size: 0.8rem;
}

/* ---- Mobile -------------------------------------------------------------- */
@media (max-width: 767px) {
  .sidebar {
    top: 4.9rem;
    left: 0.75rem;
    width: min(20rem, calc(100vw - 1.5rem));
    max-height: calc(100vh - 5.65rem);
  }
}
</style>
