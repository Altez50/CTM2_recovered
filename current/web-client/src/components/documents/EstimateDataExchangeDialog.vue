<template>
  <Modal :open="open" :title="`Обмен данными — ${title}`" size="default" @close="$emit('close')">
    <div class="tabs">
      <button class="tab" :class="{ active: mode === 'import' }" @click="mode = 'import'">Импорт</button>
      <button class="tab" :class="{ active: mode === 'export' }" @click="mode = 'export'">Экспорт</button>
    </div>

    <div class="format-row">
      <label class="format-label">Формат:</label>
      <select v-model="format" class="input">
        <option value="tsv">TSV (вкладки)</option>
        <option value="json">JSON</option>
        <option value="xlsx">XLSX (Excel)</option>
      </select>
    </div>

    <!-- IMPORT -->
    <div v-if="mode === 'import'" class="import-section">
      <p class="hint">
        Вставьте данные из буфера (Ctrl+V) или загрузите файл. Несуществующие
        работы и единицы измерения будут созданы автоматически. Строки-группы
        (с признаком «Группа» = 1) импортируются как есть.
      </p>
      <textarea
        v-if="format !== 'xlsx'"
        v-model="text"
        class="textarea"
        rows="10"
        placeholder="Код работы↹Работа↹Ед.↹Кол-во↹Цена↹Трудоёмкость↹Сумма↹План. труд"
      />
      <input
        v-else
        ref="fileInput"
        type="file"
        accept=".xlsx"
        class="file-input"
        @change="onFile"
      />
      <div class="actions">
        <label class="checkbox">
          <input v-model="replace" type="checkbox" /> Заменить существующие строки
        </label>
        <button class="button" :disabled="busy || !canImport" @click="doImport">
          {{ busy ? 'Обработка…' : previewReady ? 'Применить' : 'Проверить' }}
        </button>
      </div>
      <div v-if="result" class="result">
        <p class="ok">{{ result.preview ? 'Проверено' : 'Импортировано' }} строк: {{ result.imported }}</p>
        <ul v-if="result.warnings?.length" class="warnings">
          <li v-for="(w, i) in result.warnings" :key="i">{{ w }}</li>
        </ul>
      </div>
    </div>

    <!-- EXPORT -->
    <div v-if="mode === 'export'" class="export-section">
      <p class="hint">
        Выгрузить табличную часть сметы в выбранный формат. Поля работ
        разворачиваются в коды и наименования, включая единицы измерения.
      </p>
      <button class="button" :disabled="busy" @click="doExport">
        {{ busy ? 'Выгрузка…' : 'Скачать' }}
      </button>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Modal from '../common/Modal.vue'
import {
  type EstimateImportResult,
  exportEstimateText,
  importEstimateText,
} from '../../api/documents'

const props = defineProps<{
  open: boolean
  docId: number
  title?: string
}>()

const emit = defineEmits<{ close: []; imported: [] }>()

const mode = ref<'import' | 'export'>('import')
const format = ref<'tsv' | 'json' | 'xlsx'>('tsv')
const text = ref('')
const replace = ref(true)
const busy = ref(false)
const result = ref<EstimateImportResult | null>(null)
const previewReady = ref(false)
const fileBytes = ref<ArrayBuffer | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

const canImport = computed(() =>
  format.value === 'xlsx' ? !!fileBytes.value : text.value.trim().length > 0,
)

function onFile(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  file.arrayBuffer().then((buf) => {
    fileBytes.value = buf
  })
}

async function doImport() {
  busy.value = true
  result.value = null
  try {
    const body = format.value === 'xlsx' ? fileBytes.value! : text.value
    const preview = !previewReady.value
    const resp = await importEstimateText(props.docId, format.value, body, replace.value, preview)
    result.value = resp.data
    if (preview) {
      previewReady.value = true
    } else {
      previewReady.value = false
      emit('imported')
    }
  } catch (e) {
    result.value = { imported: 0, warnings: [(e as Error).message], format: format.value }
  } finally {
    busy.value = false
  }
}

watch([format, text, replace, fileBytes], () => {
  previewReady.value = false
  result.value = null
})

async function doExport() {
  busy.value = true
  try {
    const blob = await exportEstimateText(props.docId, format.value)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ext = format.value
    a.download = `estimate_${props.docId}.${ext}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--border);
}
.tab {
  padding: 0.5rem 1rem;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  color: var(--text-soft);
  font: inherit;
}
.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
}
.format-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.format-label {
  font-weight: 600;
}
.textarea {
  width: 100%;
  font-family: 'Consolas', monospace;
  font-size: 0.85rem;
  resize: vertical;
}
.file-input {
  width: 100%;
}
.hint {
  color: var(--text-soft);
  font-size: 0.85rem;
  margin: 0 0 0.75rem;
}
.actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1rem;
}
.checkbox {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
}
.result {
  margin-top: 1rem;
  padding: 0.75rem;
  background: var(--bg-soft);
  border-radius: 6px;
}
.ok {
  font-weight: 600;
  margin: 0 0 0.25rem;
}
.warnings {
  margin: 0;
  padding-left: 1.2rem;
  color: #b7791f;
  font-size: 0.82rem;
}
</style>
