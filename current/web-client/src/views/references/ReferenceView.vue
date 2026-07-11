<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input
            v-model="search"
            class="input toolbar-grow"
            type="search"
            :placeholder="`Поиск по разделу «${config.title}»`"
          />
          <button class="button button-primary" type="button" title="Добавить" @click="openCreate">+</button>
          <button class="button button-secondary" type="button" title="Обновить" @click="loadItems">↻</button>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar
          :selected-count="selectedIds.length"
          @deselect-all="selectedIds = []"
        >
          <button
            v-if="selectedIds.length === 1"
            class="button button-secondary"
            type="button"
            title="Изменить"
            @click="openEditById(Number(selectedIds[0]))"
          >
            ✎
          </button>
          <button
            v-if="selectedIds.length === 1"
            class="button button-secondary"
            type="button"
            title="Копировать"
            @click="openCopyById(Number(selectedIds[0]))"
          >
            ⎘
          </button>
          <button
            class="button button-danger"
            type="button"
            title="Удалить"
            @click="removeSelected"
          >
            ✕
          </button>
        </SelectionActionBar>

        <DataTable
          :columns="displayColumns"
          :rows="rows as Record<string, unknown>[]"
          :loading="loading"
          empty-text="Записей пока нет"
          selectable
          :selected-ids="selectedIds"
          @update:selected-ids="selectedIds = $event"
          @row-dblclick="handleRowDblClick"
        >
          <template #cell-name="{ row }">
            <strong>{{ getDisplayName(row as unknown as ReferenceRecord) }}</strong>
          </template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">
            Страница {{ pagination.page }} из {{ pagination.pages }}. Всего записей: {{ pagination.total }}
          </span>
          <div class="table-actions">
            <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page -= 1">
              Назад
            </button>
            <button
              class="button button-secondary"
              type="button"
              :disabled="page >= pagination.pages"
              @click="page += 1"
            >
              Вперед
            </button>
          </div>
        </div>
      </div>
    </section>

    <Modal
      :open="editorOpen"
      :title="editorMode === 'create' ? `Новый элемент: ${config.singular}` : `Редактирование: ${config.singular}`"
      @close="editorOpen = false"
    >
      <form class="page-shell" @submit.prevent="save">
        <div class="form-grid">
          <FormField v-for="field in config.fields" :key="field.key" :label="field.label">
            <template v-if="field.type === 'select'">
              <select v-model="form[field.key]" class="select">
                <option :value="null">Не выбрано</option>
                <option v-for="option in field.options?.()" :key="option.id" :value="option.id">
                  {{ option.label }}
                </option>
              </select>
            </template>
            <template v-else-if="field.type === 'checkbox'">
              <label class="checkbox-row">
                <input v-model="form[field.key]" type="checkbox" />
                <span>{{ field.checkboxLabel }}</span>
              </label>
            </template>
            <template v-else>
              <input
                v-model="form[field.key]"
                class="input"
                :type="field.type"
                :inputmode="field.type === 'number' ? 'numeric' : undefined"
              />
            </template>
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="submit" title="Сохранить">💾</button>
          <button class="button button-secondary" type="button" @click="editorOpen = false">Отмена</button>
        </div>
      </form>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { clearWorkCatalogCache } from '../../api/workCatalog'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import Modal from '../../components/common/Modal.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import { createReference, deleteReference, listReferences, updateReference } from '../../api/references'
import { useHeaderBar } from '../../composables/useHeaderBar'
import {
  buildReferencePayload,
  getReferenceConfig,
  loadReferenceHelpers,
  type ReferenceFieldHelpers,
} from '../../composables/referenceFields'
import type { HeaderAction } from '../../stores/headerBar'
import type {
  Counterparty,
  OrganizationRecord,
  PersonRecord,
  ReferenceKind,
  ReferenceRecord,
  UnitRecord,
} from '../../types/models'

const props = defineProps<{ type?: string; tabId?: string }>()

const rows = ref<ReferenceRecord[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const search = ref('')
const page = ref(1)
const pagination = reactive({ page: 1, pages: 1, total: 0 })
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)
const form = reactive<Record<string, any>>({})
const selectedIds = ref<string[]>([])

const counterparties = ref<Counterparty[]>([])
const persons = ref<PersonRecord[]>([])
const units = ref<UnitRecord[]>([])
const organizations = ref<OrganizationRecord[]>([])
const helpers: ReferenceFieldHelpers = { counterparties, persons, units, organizations }
let searchTimer = 0

const currentKind = computed<ReferenceKind>(() => {
  const value = props.type ?? 'counterparties'
  if (['counterparties', 'objects', 'works', 'persons', 'organizations', 'contracts', 'materials'].includes(value)) {
    return value as ReferenceKind
  }
  return 'counterparties'
})

const config = computed(() => getReferenceConfig(currentKind.value, helpers))

const displayColumns = computed(() => config.value.columns.filter((c) => c.key !== 'actions'))

const headerTitle = computed(() => config.value.title)
const headerActions = computed<HeaderAction[]>(() => [
  { key: 'add', icon: '+', title: 'Добавить', variant: 'primary', onClick: openCreate },
])
useHeaderBar(props.tabId, headerTitle, headerActions)

function resetForm() {
  Object.keys(form).forEach((key) => delete form[key])
  config.value.fields.forEach((field) => {
    if (field.defaultValue !== undefined) {
      form[field.key] = field.defaultValue
    } else if (field.type === 'checkbox') {
      form[field.key] = false
    } else {
      form[field.key] = null
    }
  })
}

function getDisplayName(row: ReferenceRecord) {
  if ('display_name' in row && row.display_name) {
    return row.display_name
  }
  if ('name' in row) {
    return row.name
  }
  if ('full_name' in row) {
    return row.full_name
  }
  return 'Без названия'
}

async function loadHelpers() {
  await loadReferenceHelpers(currentKind.value, helpers)
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    await loadHelpers()
    const response = await listReferences(currentKind.value, {
      page: page.value,
      page_size: 20,
      search: search.value,
    })
    rows.value =
      currentKind.value === 'persons'
        ? (response.data as PersonRecord[]).map((row) => ({ ...row, name: row.full_name }))
        : response.data
    pagination.page = response.pagination?.page ?? 1
    pagination.pages = response.pagination?.pages ?? 1
    pagination.total = response.pagination?.total ?? 0
    selectedIds.value = []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editorMode.value = 'create'
  editingId.value = null
  resetForm()
  editorOpen.value = true
}

function openEdit(row: ReferenceRecord) {
  editorMode.value = 'edit'
  editingId.value = row.id
  resetForm()
  Object.assign(form, row)
  editorOpen.value = true
}

function openEditById(id: number) {
  const row = rows.value.find((r) => r.id === id)
  if (row) openEdit(row)
}

function openCopy(row: ReferenceRecord) {
  editorMode.value = 'create'
  editingId.value = null
  resetForm()
  Object.assign(form, row)
  delete (form as Record<string, unknown>).id
  editorOpen.value = true
}

function openCopyById(id: number) {
  const row = rows.value.find((r) => r.id === id)
  if (row) openCopy(row)
}

function handleRowDblClick(row: Record<string, unknown>) {
  openEdit(row as unknown as ReferenceRecord)
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload = buildReferencePayload(form as unknown as ReferenceRecord, config.value.fields)
    if (editorMode.value === 'create') {
      await createReference(currentKind.value, payload)
    } else if (editingId.value) {
      await updateReference(currentKind.value, editingId.value, payload)
    }
    if (currentKind.value === 'works') {
      clearWorkCatalogCache()
    }
    editorOpen.value = false
    await loadItems()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сохранить запись'
  } finally {
    saving.value = false
  }
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'запись' : `${selectedIds.value.length} записей`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return

  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await deleteReference(currentKind.value, Number(id))
    } catch {
      failed++
    }
  }
  if (currentKind.value === 'works') {
    clearWorkCatalogCache()
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось удалить ${failed} из ${selectedIds.value.length + failed} записей`
  }
}

watch([currentKind, page], loadItems)
watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    loadItems()
  }, 300)
})

onMounted(async () => {
  resetForm()
  await loadItems()
})
</script>

<style scoped>
.pagination-row {
  justify-content: space-between;
  margin-top: 1rem;
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}
</style>
