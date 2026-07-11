<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <select v-model="targetFilter" class="select">
            <option value="goods_receipt">Поступления ТМЦ</option>
            <option value="goods_issue">Списания ТМЦ</option>
            <option value="work_specification">Спецификация работ</option>
          </select>
          <button class="button button-secondary" type="button" title="Обновить" @click="load">↻</button>
          <div class="toolbar-grow"></div>
          <button class="button button-primary" type="button" @click="openCreate">+ Создать профиль</button>
        </div>

        <p v-if="error" class="message-banner message-error">{{ error }}</p>
        <p v-if="info" class="message-banner message-success">{{ info }}</p>

        <DataTable :columns="columns" :rows="rows as Record<string, unknown>[]" :loading="loading" empty-text="Профилей пока нет. Создайте первый.">
          <template #cell-create_missing_materials="{ row }">{{ (row as unknown as ImportProfile).create_missing_materials ? 'да' : 'нет' }}</template>
          <template #cell-actions="{ row }">
            <div class="table-actions">
              <button class="button button-secondary" type="button" title="Изменить" @click="openEdit(row as unknown as ImportProfile)">✎</button>
              <button class="button button-danger" type="button" title="Удалить" @click="remove(row as unknown as ImportProfile)">✕</button>
            </div>
          </template>
        </DataTable>
      </div>
    </section>

    <Modal :open="editorOpen" size="full" :title="editing?.name ? `Профиль: ${editing.name}` : 'Новый профиль импорта'" @close="editorOpen = false">
      <div class="modal-stack">
        <div v-if="editorError" class="message-banner message-error">{{ editorError }}</div>
        <div class="form-grid">
          <FormField label="Имя профиля">
            <input v-model="draft.name" class="input" type="text" placeholder="Напр. Спецификация (Приложение №1)" />
          </FormField>
          <FormField label="Назначение (target)">
            <select v-model="draft.target" class="select">
              <option value="goods_receipt">Поступления ТМЦ</option>
              <option value="goods_issue">Списания ТМЦ</option>
              <option value="work_specification">Спецификация работ</option>
            </select>
          </FormField>
          <FormField label="Лист (имя или индекс)">
            <input v-model="draft.sheet" class="input" type="text" placeholder="пусто = активный лист; 0 = первый" />
          </FormField>
          <FormField label="Строка заголовков">
            <input v-model.number="draft.header_row" class="input" type="number" min="1" />
          </FormField>
          <FormField label="Данные с (строка)">
            <input v-model.number="draft.data_start_row" class="input" type="number" min="1" placeholder="пусто = header_row+1" />
          </FormField>
          <FormField label="Колонка-множитель цены (вес)">
            <input v-model.number="draft.price_multiplier_column" class="input" type="number" min="1" placeholder="пусто = нет" />
          </FormField>
          <FormField label="Колонка суммы без НДС">
            <input v-model.number="draft.sum_column" class="input" type="number" min="1" placeholder="пусто = считать" />
          </FormField>
          <FormField label="Разрешение материала">
            <select v-model="draft.material_resolve_by" class="select">
              <option value="code_or_name">По коду или имени</option>
              <option value="code">По коду</option>
              <option value="name">По имени</option>
              <option value="none">Не разрешать</option>
            </select>
          </FormField>
          <FormField label="Создавать материалы" class="checkbox-field">
            <label class="checkbox-row"><input v-model="draft.create_missing_materials" type="checkbox" /><span>Создавать отсутствующие материалы</span></label>
          </FormField>
          <FormField label="Создавать единицы" class="checkbox-field">
            <label class="checkbox-row"><input v-model="draft.create_missing_units" type="checkbox" /><span>Создавать отсутствующие единицы</span></label>
          </FormField>
          <FormField label="Стоп по пустому имени" class="checkbox-field">
            <label class="checkbox-row"><input v-model="draft.stop_on_first_empty_name" type="checkbox" /><span>Останавливать чтение на первой пустой строке</span></label>
          </FormField>
        </div>

        <FormField label="Описание">
          <input v-model="draft.description" class="input" type="text" />
        </FormField>

        <h4>Маппинг колонок (поле → № колонки в Excel)</h4>
        <div class="mapping-grid">
          <div v-for="field in mappableFields" :key="field.key" class="mapping-row">
            <span class="mapping-label">{{ field.label }}</span>
            <input v-model.number="columnMapping[field.key]" class="input mapping-input" type="number" min="1" placeholder="—" />
          </div>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" title="Сохранить" @click="saveDraft">💾</button>
          <button class="button button-secondary" type="button" @click="editorOpen = false">Отмена</button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import Modal from '../../components/common/Modal.vue'
import { deleteImportProfile, listImportProfiles, saveImportProfile } from '../../api/goods'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { ImportProfile, ImportProfileTarget } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Профили импорта Excel'), computed(() => []))

const rows = ref<ImportProfile[]>([])
const loading = ref(false)
const error = ref('')
const info = ref('')
const targetFilter = ref<ImportProfileTarget>('goods_receipt')

const editorOpen = ref(false)
const editorError = ref('')
const editing = ref<ImportProfile | null>(null)
const draft = reactive<ImportProfile>(emptyDraft())
const columnMapping = reactive<Record<string, number | undefined>>({})

const columns = [
  { key: 'name', label: 'Имя' },
  { key: 'target', label: 'Назначение' },
  { key: 'header_row', label: 'Строка шапки' },
  { key: 'data_start_row', label: 'Данные с' },
  { key: 'price_multiplier_column', label: 'Множитель цены' },
  { key: 'material_resolve_by', label: 'Разрешение материала' },
  { key: 'create_missing_materials', label: 'Создавать материалы' },
  { key: 'description', label: 'Описание' },
  { key: 'actions', label: '' },
]

const mappableFields = [
  { key: 'name', label: 'Наименование' },
  { key: 'material_id', label: 'Материал (id)' },
  { key: 'material_code', label: 'Код материала' },
  { key: 'unit', label: 'Ед. изм.' },
  { key: 'quantity', label: 'Количество' },
  { key: 'price_without_vat', label: 'Цена без НДС' },
  { key: 'vat_rate', label: 'Ставка НДС %' },
  { key: 'sum_without_vat', label: 'Сумма без НДС' },
  { key: 'object_id', label: 'Объект' },
  { key: 'drawing_code', label: 'Чертёж/СП' },
  { key: 'note', label: 'Примечание' },
]

function emptyDraft(): ImportProfile {
  return {
    name: '',
    target: 'goods_receipt',
    sheet: null,
    header_row: 1,
    data_start_row: null,
    data_end_row: null,
    column_mapping: {},
    overrides: { vat_rate: 20 },
    price_multiplier_column: null,
    sum_column: null,
    sum_with_vat_column: null,
    skip_rules: [],
    material_resolve_by: 'code_or_name',
    create_missing_materials: false,
    create_missing_units: false,
    stop_on_first_empty_name: false,
    description: '',
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listImportProfiles(targetFilter.value)
    rows.value = res.data
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(draft, emptyDraft())
  draft.target = targetFilter.value
  Object.keys(columnMapping).forEach((k) => delete columnMapping[k])
  editorError.value = ''
  editorOpen.value = true
}

function openEdit(profile: ImportProfile) {
  editing.value = profile
  Object.assign(draft, emptyDraft(), JSON.parse(JSON.stringify(profile)))
  Object.keys(columnMapping).forEach((k) => delete columnMapping[k])
  Object.entries(profile.column_mapping || {}).forEach(([k, v]) => { columnMapping[k] = v })
  editorError.value = ''
  editorOpen.value = true
}

async function saveDraft() {
  editorError.value = ''
  if (!draft.name.trim()) {
    editorError.value = 'Укажите имя профиля'
    return
  }
  const payload = { ...draft } as ImportProfile
  // column_mapping: keep only numeric values
  const mapping: Record<string, number> = {}
  Object.entries(columnMapping).forEach(([k, v]) => {
    if (typeof v === 'number' && v > 0) mapping[k] = v
  })
  payload.column_mapping = mapping
  // drop empty-number fields → null
  const nullable = payload as unknown as Record<string, unknown>
  ;(['price_multiplier_column', 'sum_column', 'sum_with_vat_column', 'data_start_row', 'data_end_row'] as const).forEach((k) => {
    if (nullable[k] === undefined || nullable[k] === 0) nullable[k] = null
  })
  try {
    await saveImportProfile(payload)
    info.value = `Профиль «${payload.name}» сохранён`
    editorOpen.value = false
    await load()
  } catch (err) {
    editorError.value = err instanceof Error ? err.message : 'Ошибка сохранения'
  }
}

async function remove(profile: ImportProfile) {
  if (!window.confirm(`Удалить профиль «${profile.name}»?`)) return
  try {
    await deleteImportProfile(profile.name, profile.target)
    info.value = 'Профиль удалён'
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка удаления'
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1rem; }
.checkbox-field { grid-column: span 1; }
.checkbox-row { display: flex; align-items: center; gap: 0.4rem; }
.mapping-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.4rem 1rem; margin: 0.5rem 0 1rem; }
.mapping-row { display: flex; flex-direction: column; gap: 0.2rem; }
.mapping-label { font-size: 0.8rem; color: var(--muted, #666); }
.mapping-input { width: 100%; box-sizing: border-box; }
.message-banner { padding: 0.5rem 0.75rem; border-radius: 4px; margin-bottom: 0.75rem; }
.message-error { background: var(--danger-bg, #fde8e8); color: var(--danger, #b00020); }
.message-success { background: var(--success-bg, #e8f5e9); color: var(--success, #1b7a3d); }
h4 { margin: 0.5rem 0; }
</style>
