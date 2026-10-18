import type { Ref } from 'vue'
import { listReferences } from '../api/references'
import { listUnits } from '../api/works'
import type { ReferenceKind } from '../types/models'

export type ReferenceRecordLike = Record<string, any>

export type FieldConfig = {
  key: string
  label: string
  type: 'text' | 'number' | 'select' | 'checkbox' | 'reference-picker'
  checkboxLabel?: string
  defaultValue?: string | number | boolean | null
  options?: () => Array<{ id: number; label: string }>
  referenceKind?: ReferenceKind
  referenceLabelKey?: string
  selectedLabelKey?: string
  referenceCaptionKey?: string
  pickerTitle?: string
}

export type Column = {
  key: string
  label: string
}

export interface ReferenceFieldHelpers {
  counterparties: Ref<ReferenceRecordLike[]>
  persons: Ref<ReferenceRecordLike[]>
  units: Ref<ReferenceRecordLike[]>
  organizations: Ref<ReferenceRecordLike[]>
}

export interface ReferenceConfig {
  title: string
  singular: string
  description: string
  modalDescription: string
  fields: FieldConfig[]
  columns: Column[]
}

export function getReferenceConfig(kind: ReferenceKind, h: ReferenceFieldHelpers, isAdmin = true): ReferenceConfig {
  const sharedTail: FieldConfig[] = [
    { key: 'parent_id', label: 'Родительская группа (ID)', type: 'number' },
    { key: 'is_group', label: 'Тип записи', type: 'checkbox', checkboxLabel: 'Это группа' },
  ]
  const mapping: Record<ReferenceKind, ReferenceConfig> = {
    'material-packages': {
      title: 'Упаковки товаров', singular: 'упаковка', description: 'Количество базовых единиц в одной упаковке.',
      modalDescription: 'Цена в документе задается за упаковку. После использования коэффициент изменить нельзя.',
      fields: [
        { key: 'name', label: 'Наименование', type: 'text' },
        { key: 'material_id', label: 'Товар', type: 'reference-picker', referenceKind: 'materials', referenceLabelKey: 'name', selectedLabelKey: 'material_name' },
        { key: 'factor', label: 'Базовых единиц в упаковке', type: 'number', defaultValue: 1 },
      ], columns: [{ key: 'name', label: 'Упаковка' }, { key: 'material_name', label: 'Товар' }, { key: 'factor', label: 'Коэффициент' }, { key: 'actions', label: 'Действия' }],
    },
    'material-characteristics': {
      title: 'Характеристики товаров', singular: 'характеристика', description: 'Отдельные складские остатки и себестоимость по характеристикам.',
      modalDescription: 'Характеристика принадлежит конкретному товару.',
      fields: [{ key: 'name', label: 'Наименование', type: 'text' },
        { key: 'material_id', label: 'Товар', type: 'reference-picker', referenceKind: 'materials', referenceLabelKey: 'name', selectedLabelKey: 'material_name' }],
      columns: [{ key: 'name', label: 'Характеристика' }, { key: 'material_name', label: 'Товар' }, { key: 'actions', label: 'Действия' }],
    },
    'material-series': {
      title: 'Серии товаров', singular: 'серия', description: 'Остатки и себестоимость по сериям товара.',
      modalDescription: 'Можно ограничить серию конкретной характеристикой.',
      fields: [{ key: 'name', label: 'Наименование', type: 'text' },
        { key: 'material_id', label: 'Товар', type: 'reference-picker', referenceKind: 'materials', referenceLabelKey: 'name', selectedLabelKey: 'material_name' },
        { key: 'characteristic_id', label: 'Характеристика', type: 'reference-picker', referenceKind: 'material-characteristics', referenceLabelKey: 'name', selectedLabelKey: 'characteristic_name' }],
      columns: [{ key: 'name', label: 'Серия' }, { key: 'material_name', label: 'Товар' }, { key: 'actions', label: 'Действия' }],
    },
    counterparties: {
      title: 'Контрагенты',
      singular: 'контрагент',
      description: 'Заказчики, владельцы объектов и контактные лица.',
      modalDescription: 'Поддерживаются поисковые поля и мягкое удаление.',
      fields: [
        { key: 'name', label: 'Наименование', type: 'text' },
        { key: 'inn', label: 'ИНН', type: 'text' },
        { key: 'contact_person', label: 'Контактное лицо', type: 'text' },
        { key: 'phone', label: 'Телефон', type: 'text' },
        ...sharedTail,
      ],
      columns: [
        { key: 'name', label: 'Наименование' },
        { key: 'inn', label: 'ИНН' },
        { key: 'contact_person', label: 'Контакт' },
        { key: 'phone', label: 'Телефон' },
        { key: 'actions', label: 'Действия' },
      ],
    },
    objects: {
      title: 'Объекты',
      singular: 'объект',
      description: 'Строительные площадки, адреса и связь с владельцем.',
      modalDescription: 'Для владельца используется справочник контрагентов.',
      fields: [
        { key: 'name', label: 'Наименование', type: 'text' },
        { key: 'address', label: 'Адрес', type: 'text' },
        {
          key: 'owner_id',
          label: 'Владелец',
          type: 'select',
          options: () => h.counterparties.value.map((item) => ({ id: item.id, label: item.name })),
        },
        ...sharedTail,
      ],
      columns: [
        { key: 'name', label: 'Объект' },
        { key: 'address', label: 'Адрес' },
        { key: 'owner_name', label: 'Владелец' },
        { key: 'actions', label: 'Действия' },
      ],
    },
    works: {
      title: 'Работы',
      singular: 'работа',
      description: 'Нормативные работы с кодами, единицами и расценками.',
      modalDescription: 'Цена и трудоемкость используются в документах и регистре.',
      fields: [
        { key: 'name', label: 'Наименование', type: 'text' },
        { key: 'code', label: 'Код', type: 'text' },
        { key: 'unit', label: 'Единица', type: 'text' },
        { key: 'price', label: 'Цена', type: 'number' },
        { key: 'labor_rate', label: 'Норма труда', type: 'number' },
        ...sharedTail,
      ],
      columns: [
        { key: 'name', label: 'Работа' },
        { key: 'code', label: 'Код' },
        { key: 'unit', label: 'Ед.' },
        { key: 'price', label: 'Цена' },
        { key: 'labor_rate', label: 'Трудоемкость' },
        { key: 'actions', label: 'Действия' },
      ],
    },
    persons: {
      title: 'Физические лица',
      singular: 'физлицо',
      description: 'Сотрудники, исполнители и прорабы для отчетов и документов.',
      modalDescription: 'Ставка используется в табелях как значение по умолчанию.',
      fields: [
        { key: 'full_name', label: 'ФИО', type: 'text' },
        { key: 'personnel_number', label: 'Табельный номер', type: 'text' },
        { key: 'position', label: 'Должность', type: 'text' },
        { key: 'phone', label: 'Телефон', type: 'text' },
        { key: 'hourly_rate', label: 'Ставка, руб/час', type: 'number', defaultValue: 0 },
        ...sharedTail,
      ],
      columns: [
        { key: 'name', label: 'ФИО' },
        { key: 'personnel_number', label: 'Таб. номер' },
        { key: 'position', label: 'Должность' },
        { key: 'phone', label: 'Телефон' },
        { key: 'hourly_rate', label: 'Ставка' },
        { key: 'actions', label: 'Действия' },
      ],
    },
    organizations: {
      title: 'Организации',
      singular: 'организация',
      description: 'Подрядчики и вложенные структуры компаний.',
      modalDescription: 'Ответственный выбирается из справочника физических лиц.',
      fields: [
        { key: 'name', label: 'Наименование', type: 'text' },
        { key: 'inn', label: 'ИНН', type: 'text' },
        {
          key: 'default_responsible_id',
          label: 'Ответственный',
          type: 'select',
          options: () => h.persons.value.map((item) => ({ id: item.id, label: item.full_name })),
        },
        ...sharedTail,
      ],
      columns: [
        { key: 'name', label: 'Организация' },
        { key: 'inn', label: 'ИНН' },
        { key: 'default_responsible_name', label: 'Ответственный' },
        { key: 'actions', label: 'Действия' },
      ],
    },
    contracts: {
      title: 'Договоры',
      singular: 'договор',
      description: 'Договоры и доп. соглашения (для взаиморасчетов).',
      modalDescription: 'Тип определяет направление: supply — закупка (кредиторка), sales — реализация (дебиторка).',
      fields: [
        { key: 'number', label: 'Номер', type: 'text' },
        { key: 'date', label: 'Дата', type: 'text' },
        {
          key: 'organization_id',
          label: 'Наша организация',
          type: 'select',
          options: () => h.organizations.value.map((item) => ({ id: item.id, label: item.name })),
        },
        {
          key: 'counterparty_id',
          label: 'Контрагент',
          type: 'select',
          options: () => h.counterparties.value.map((item) => ({ id: item.id, label: item.name })),
        },
        { key: 'kind', label: 'Тип (supply/sales/mixed/other)', type: 'text', defaultValue: 'supply' },
        { key: 'amount', label: 'Сумма', type: 'number', defaultValue: 0 },
        { key: 'vat_rate', label: 'НДС, %', type: 'number', defaultValue: 20 },
        { key: 'payment_deferral_days', label: 'Отсрочка оплаты, дней', type: 'number', defaultValue: 0 },
        { key: 'credit_limit', label: 'Кредитный лимит (администратор)', type: 'number', defaultValue: null },
        { key: 'credit_limit_strict', label: 'Контроль кредита', type: 'checkbox', checkboxLabel: 'Строгий лимит договора', defaultValue: false },
        { key: 'currency', label: 'Валюта', type: 'text', defaultValue: 'RUB' },
        { key: 'agreement_date', label: 'Дата договора', type: 'text' },
        { key: 'valid_until', label: 'Срок действия', type: 'text' },
        { key: 'description', label: 'Описание', type: 'text' },
        {
          key: 'parent_id',
          label: 'Родительский договор',
          type: 'reference-picker',
          referenceKind: 'contracts',
          referenceLabelKey: 'number',
          selectedLabelKey: 'parent_number',
          referenceCaptionKey: 'counterparty_name',
          pickerTitle: 'Выбор родительского договора',
        },
      ],
      columns: [
        { key: 'number', label: 'Номер' },
        { key: 'date', label: 'Дата' },
        { key: 'organization_name', label: 'Организация' },
        { key: 'counterparty_name', label: 'Контрагент' },
        { key: 'kind', label: 'Тип' },
        { key: 'amount', label: 'Сумма' },
        { key: 'vat_rate', label: 'НДС %' },
        { key: 'payment_deferral_days', label: 'Отсрочка' },
        { key: 'actions', label: 'Действия' },
      ],
    },
    materials: {
      title: 'Материалы',
      singular: 'материал',
      description: 'Материалы: коды, единицы измерения и цены.',
      modalDescription: 'Единица измерения выбирается из справочника единиц.',
      fields: [
        { key: 'name', label: 'Наименование', type: 'text' },
        { key: 'code', label: 'Код', type: 'text' },
        {
          key: 'unit_id',
          label: 'Единица измерения',
          type: 'select',
          options: () => h.units.value.map((item) => ({ id: item.id, label: item.name })),
        },
        { key: 'price', label: 'Цена', type: 'number', defaultValue: 0 },
        ...sharedTail,
      ],
      columns: [
        { key: 'name', label: 'Наименование' },
        { key: 'code', label: 'Код' },
        { key: 'unit_name', label: 'Единица' },
        { key: 'price', label: 'Цена' },
        { key: 'parent_name', label: 'Папка' },
        { key: 'is_group', label: 'Группа' },
        { key: 'actions', label: 'Действия' },
      ],
    },
    warehouses: {
      title: 'Склады',
      singular: 'склад',
      description: 'Места хранения ТМЦ по организациям.',
      modalDescription: 'Склад используется в поступлениях, списаниях и перемещениях ТМЦ.',
      fields: [
        { key: 'order_receipt_enabled', label: 'Схема приемки', type: 'checkbox', checkboxLabel: 'Отдельный приходный ордер', defaultValue: false },
        { key: 'order_issue_enabled', label: 'Схема отгрузки', type: 'checkbox', checkboxLabel: 'Отдельный расходный ордер', defaultValue: false },
        { key: 'name', label: 'Наименование', type: 'text' },
        { key: 'code', label: 'Код', type: 'text', defaultValue: '' },
        { key: 'organization_id', label: 'Организация', type: 'select',
          options: () => h.organizations.value.map((item) => ({ id: item.id, label: item.name })) },
        { key: 'default_object_id', label: 'Объект по умолчанию', type: 'reference-picker',
          referenceKind: 'objects', referenceLabelKey: 'name', selectedLabelKey: 'default_object_name', pickerTitle: 'Выбор объекта' },
        { key: 'responsible_id', label: 'Ответственный', type: 'reference-picker',
          referenceKind: 'persons', referenceLabelKey: 'full_name', selectedLabelKey: 'responsible_name', pickerTitle: 'Выбор ответственного' },
        { key: 'address', label: 'Адрес', type: 'text' },
      ],
      columns: [
        { key: 'name', label: 'Наименование' },
        { key: 'code', label: 'Код' },
        { key: 'organization_name', label: 'Организация' },
        { key: 'default_object_name', label: 'Объект' },
        { key: 'responsible_name', label: 'Ответственный' },
        { key: 'actions', label: 'Действия' },
      ],
    },
  }
  const result = mapping[kind]
  if (kind === 'contracts' && !isAdmin) result.fields = result.fields.filter(field => !['credit_limit', 'credit_limit_strict'].includes(field.key))
  return result
}

export async function loadReferenceHelpers(kind: ReferenceKind, h: ReferenceFieldHelpers): Promise<void> {
  if (kind === 'objects' || kind === 'counterparties' || kind === 'contracts') {
    const response = await listReferences('counterparties', { page_size: 50 })
    h.counterparties.value = response.data as ReferenceRecordLike[]
  }
  if (kind === 'contracts' || kind === 'warehouses') {
    const response = await listReferences('organizations', { page_size: 50 })
    h.organizations.value = response.data as ReferenceRecordLike[]
  }
  if (kind === 'organizations' || kind === 'persons') {
    const response = await listReferences('persons', { page_size: 50 })
    h.persons.value = response.data as ReferenceRecordLike[]
  }
  if (kind === 'materials') {
    const response = await listUnits()
    h.units.value = response.data as ReferenceRecordLike[]
  }
}

export function buildReferencePayload(form: ReferenceRecordLike, fields: FieldConfig[]): ReferenceRecordLike {
  const analytic = fields.some(field => field.key === 'material_id' && field.referenceKind === 'materials')
  const payload = analytic ? Object.fromEntries(fields.map(field => [field.key, form[field.key]])) : { ...form }
  fields.forEach((field) => {
    if (field.type === 'number') {
      payload[field.key] =
        payload[field.key] === null || payload[field.key] === ''
          ? (field.defaultValue ?? null)
          : Number(payload[field.key])
    }
  })
  return payload
}
