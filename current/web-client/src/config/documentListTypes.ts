/**
 * Декларативная конфигурация списка документов (DOCUMENT_LIST_SPEC.md, раздел 5.2).
 * Каждый вид документа описывается одним объектом DocListConfig; поведение списка
 * (сортировка, отбор, состав колонок, команды, «Ввод на основании») едино для всех.
 */
import type { FilterOption, ColumnFilter } from '../components/common/DataTable.vue'
import type { ApiResponse } from '../types/api'

export type FilterType = ColumnFilter['type']

export interface DocListColumn {
  /** Ключ поля в данных строки (он же клиентский ключ сортировки/отбора). */
  key: string
  label: string
  sortable?: boolean
  /** Колонка доступна для быстрого отбора (появляется поле в строке отбора). */
  filterable?: boolean
  filter?: {
    type: FilterType
    placeholder?: string
    options?: FilterOption[]
  }
  /** Видимость по умолчанию (true). Пользователь меняет в «Настройка списка». */
  defaultVisible?: boolean
  /** Runtime-видимость (проставляется useListSettings из сохранённых настроек). */
  visible?: boolean
}

export interface BaseOnTarget {
  /** doc_kind документа-результата. */
  kind: string
  label: string
  /** Роут формы создания результата. */
  createRoute: string
}

export interface DocListRow {
  id?: number | string
  number?: string
  date?: string | null
  is_posted?: boolean
  marked_for_deletion?: boolean
  [key: string]: unknown
}

export interface DocListApi {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  list: (params: Record<string, string | number | undefined>) => Promise<ApiResponse<any[]>>
  post?: (id: number) => Promise<unknown>
  unpost?: (id: number) => Promise<unknown>
  remove?: (id: number) => Promise<unknown>
  restore?: (id: number) => Promise<unknown>
  copy?: (id: number) => Promise<ApiResponse<any>>
}

export interface DocListConfig {
  /** doc_kind — он же form_name для настроек пользователя. */
  formName: string
  title: string
  createLabel: string
  createRoute: string
  /** Построить роут открытия документа по id. */
  itemRoute: (id: number | string) => string
  /** Документы с проведением (по умолчанию true). */
  hasPost?: boolean
  defaultSort: { key: string; order: 'asc' | 'desc' }
  api: DocListApi
  columns: DocListColumn[]
  baseOn?: BaseOnTarget[]
  /** Разрешено ли текущему пользователю создавать документы этого вида. */
  canCreate?: (user: { role?: string; person_id?: number | null } | null) => boolean
  /** Склонённые подписи для диалогов подтверждения («Пометить смету на удаление?»). */
  labels: { one: string; few: string; many: string }
  /**
   * Доступность команд проведения для строки. По умолчанию — isAdmin для документов
   * с проведением; табели переопределяют (бригадир — только свои).
   * Возвращает true, если текущему пользователю разрешено проводить/отменять.
   */
  canManagePosting?: (user: { role?: string; person_id?: number | null } | null, row: DocListRow) => boolean
  /** Ролевая/владельческая проверка удаления строки; проверка состояния задаётся отдельно. */
  canDelete?: (user: { role?: string; person_id?: number | null } | null, row: DocListRow) => boolean
  /** Доп. параметры list-запроса, специфичные для вида (object_id и т.п.). */
  extraQuery?: () => Record<string, string | number | undefined>
  /** Поле статуса проведения (по умолчанию 'is_posted'). */
  statusField?: string
  /** Строку можно провести (по умолчанию — не проведена). Для расчёта себестоимости: status==='calculated'. */
  postableWhen?: (row: DocListRow) => boolean
  /** Строку можно «распровести» (по умолчанию — проведена). */
  postedWhen?: (row: DocListRow) => boolean
  /** Строку можно пометить на удаление (по умолчанию — не проведена). */
  canDeleteWhen?: (row: DocListRow) => boolean
  /** Разрешить «Открыть»/дабл-клик (по умолчанию true). У платежей-транзакций нет формы. */
  canOpen?: boolean
}
