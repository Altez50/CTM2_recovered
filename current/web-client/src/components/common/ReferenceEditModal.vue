<template>
  <Modal :open="open" :title="isCreate ? `Создать: ${config.title}` : `Изменить: ${config.title}`" @close="$emit('close')">
    <p class="modal-description">{{ config.modalDescription }}</p>
    <p v-if="error" class="modal-error">{{ error }}</p>
    <form class="reference-form" @submit.prevent="save">
      <FormField
        v-for="field in config.fields"
        :key="field.key"
        :label="field.label"
        :hint="field.type === 'checkbox' ? field.checkboxLabel : undefined"
      >
        <EntityPicker
          v-if="field.type === 'reference-picker'"
          :model-value="pickerModelValue(field.key)"
          :selected-label="pickerSelectedLabel(field)"
          :title="field.pickerTitle || `Выбор: ${field.label}`"
          placeholder="Не выбрано"
          search-placeholder="Поиск по номеру или описанию…"
          empty-text="Договоры не найдены"
          :load-page="(params) => loadPickerPage(field, params)"
          @update:model-value="form[field.key] = $event"
          @change="(item) => updatePickerSelection(field, item)"
        />
        <input
          v-else-if="field.type === 'text'"
          v-model="form[field.key]"
          class="input"
          type="text"
        />
        <input
          v-else-if="field.type === 'number'"
          v-model="form[field.key]"
          class="input"
          type="number"
          step="any"
        />
        <select v-else-if="field.type === 'select'" v-model="form[field.key]" class="input">
          <option :value="null">— не выбрано —</option>
          <option v-for="option in field.options ? field.options() : []" :key="option.id" :value="option.id">
            {{ option.label }}
          </option>
        </select>
        <label v-else-if="field.type === 'checkbox'" class="checkbox-line">
          <input v-model="form[field.key]" type="checkbox" />
          <span>{{ field.checkboxLabel || 'Да' }}</span>
        </label>
      </FormField>
      <div class="form-actions">
        <button class="button button-primary" type="submit" :disabled="saving">
          {{ saving ? 'Сохранение…' : 'Сохранить' }}
        </button>
        <button class="button button-secondary" type="button" @click="$emit('close')">Отмена</button>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'
import { computed, defineAsyncComponent, reactive, ref, watch } from 'vue'
import FormField from './FormField.vue'
import Modal from './Modal.vue'
import type { PickerItem } from './EntityPicker.vue'
import { listReferences, getReference, updateReference, createReference } from '../../api/references'
import {
  buildReferencePayload,
  getReferenceConfig,
  loadReferenceHelpers,
  type FieldConfig,
  type ReferenceFieldHelpers,
  type ReferenceRecordLike,
} from '../../composables/referenceFields'
import type { ReferenceKind } from '../../types/models'

const props = defineProps<{
  open: boolean
  kind: ReferenceKind
  id: number | null
}>()

const emit = defineEmits<{
  close: []
  saved: [record: ReferenceRecordLike]
}>()

const EntityPicker = defineAsyncComponent(() => import('./EntityPicker.vue'))

const counterparties = ref<ReferenceRecordLike[]>([])
const persons = ref<ReferenceRecordLike[]>([])
const units = ref<ReferenceRecordLike[]>([])
const organizations = ref<ReferenceRecordLike[]>([])
const helpers: ReferenceFieldHelpers = { counterparties, persons, units, organizations }

const config = getReferenceConfig(props.kind, helpers, useAuthStore().isAdmin)
const isCreate = computed(() => props.id === null || props.id === undefined)
const form = reactive<ReferenceRecordLike>({})
const saving = ref(false)
const error = ref('')

async function loadItem(id: number) {
  if (['material-packages', 'material-characteristics', 'material-series'].includes(props.kind)) {
    Object.assign(form, (await getReference(props.kind, id)).data)
    return
  }
  const response = await listReferences(props.kind, { search: String(id), page: 1, page_size: 50 })
  const match = (response.data as ReferenceRecordLike[]).find((item) => item.id === id)
  if (!match) {
    throw new Error('Элемент не найден')
  }
  Object.assign(form, match)
}

function pickerModelValue(key: string): number | null {
  const value = form[key]
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function pickerSelectedLabel(field: FieldConfig): string | null {
  if (!field.selectedLabelKey) return null
  const value = form[field.selectedLabelKey]
  return value === null || value === undefined || value === '' ? null : String(value)
}

async function loadPickerPage(
  field: FieldConfig,
  params: { search: string; page: number; pageSize: number },
) {
  if (!field.referenceKind || !field.referenceLabelKey) {
    return { items: [], pages: 1 }
  }
  const response = await listReferences(field.referenceKind, {
    search: params.search,
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    ...(field.referenceKind === 'material-characteristics' ? { material_id: Number(form.material_id) || undefined } : {}),
  })
  const currentId = props.kind === field.referenceKind ? props.id : null
  return {
    items: (response.data as Record<string, any>[])
      .filter((item) => item.id !== currentId)
      .map((item) => ({
        id: Number(item.id),
        label: String(item[field.referenceLabelKey!] ?? ''),
        caption: field.referenceCaptionKey ? (item[field.referenceCaptionKey] ?? null) : null,
      })),
    pages: response.pagination?.pages ?? 1,
  }
}

function updatePickerSelection(field: FieldConfig, item: PickerItem | null) {
  if (props.kind === 'material-series' && field.key === 'material_id') {
    form.characteristic_id = null; form.characteristic_name = null
  }
  form[field.key] = item?.id ?? null
  if (field.selectedLabelKey) {
    form[field.selectedLabelKey] = item?.label ?? null
  }
}

watch(
  () => [props.open, props.id],
  async ([isOpen, id]) => {
    if (!isOpen) return
    error.value = ''
    saving.value = false
    Object.keys(form).forEach((key) => delete (form as Record<string, unknown>)[key])
    try {
      await loadReferenceHelpers(props.kind, helpers)
      if (id === null || id === undefined) {
        config.fields.forEach((field) => {
          ;(form as Record<string, unknown>)[field.key] = field.defaultValue ?? null
        })
      } else {
        await loadItem(id as number)
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Не удалось загрузить запись'
    }
  },
  { immediate: true },
)

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload = buildReferencePayload(form, config.fields)
    const response = isCreate.value
      ? await createReference(props.kind, payload)
      : await updateReference(props.kind, props.id!, payload)
    emit('saved', response.data as ReferenceRecordLike)
    emit('close')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сохранить запись'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-description {
  margin: 0 0 1rem;
  color: var(--text-soft);
}

.modal-error {
  margin: 0 0 1rem;
  color: var(--danger);
}

.reference-form {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.checkbox-line {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.form-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
