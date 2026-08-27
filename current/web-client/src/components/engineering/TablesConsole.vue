<template>
  <div class="eng-split console-split">
    <aside class="panel eng-side">
      <EngineeringTableTree
        :catalog="catalog"
        qualified
        @select-table="onSelectTable"
        @insert-token="insertToken"
      />
    </aside>

    <section class="panel eng-main console-main">
      <div class="panel-body console-body">
        <!-- Панель действий -->
        <div class="toolbar console-toolbar">
          <button class="button button-primary" type="button" :disabled="running" title="Выполнить (Ctrl+Enter)" @click="run">
            ▶ Выполнить
          </button>
          <button class="button button-secondary" type="button" title="Очистить" @click="clearEditor">Очистить</button>
          <button class="button button-secondary" type="button" title="Сохранить запрос" @click="saveCurrent">Сохранить</button>
          <div v-if="savedQueries.length" class="saved-wrap">
            <button class="button button-secondary" type="button" @click="savedOpen = !savedOpen">Сохранённые ▾</button>
            <ul v-if="savedOpen" class="saved-menu panel" @click.stop>
              <li v-for="q in savedQueries" :key="q.id" class="saved-item">
                <button type="button" class="saved-load" :title="q.text" @click="loadSaved(q.id)">{{ q.name }}</button>
                <button type="button" class="saved-del" title="Удалить" @click="deleteSaved(q.id)">✕</button>
              </li>
            </ul>
          </div>
          <span v-if="result" class="muted console-meta">
            {{ result.row_count }} строк · {{ result.elapsed_ms }} мс
            <span v-if="result.truncated" class="trunc">(обрезано по лимиту)</span>
          </span>
        </div>

        <!-- Редактор -->
        <textarea
          ref="editorRef"
          v-model="text"
          class="console-editor"
          spellcheck="false"
          placeholder="SELECT Наименование, ИНН FROM Контрагенты LIMIT 10"
          @keydown="onEditorKey"
        ></textarea>

        <p v-if="error" class="console-error">{{ error }}</p>

        <!-- Результат -->
        <div v-if="result" class="console-result">
          <DataTable
            :columns="resultColumns"
            :rows="result.rows"
            empty-text="Запрос вернул 0 строк"
          />
          <div v-if="numericTotals.length" class="console-totals">
            <span v-for="t in numericTotals" :key="t.label" class="total-chip">
              {{ t.label }}: Σ={{ t.sum }} ({{ t.avg }} ср.)
            </span>
          </div>
          <div class="toolbar console-result-actions">
            <button class="button button-secondary" type="button" @click="printResult">Печать</button>
            <button class="button button-secondary" type="button" @click="exportCsv">Экспорт CSV</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import DataTable from '../common/DataTable.vue'
import type { Column } from '../common/DataTable.vue'
import EngineeringTableTree from './EngineeringTableTree.vue'
import { executeQuery, type EngineeringCatalog, type QueryResult } from '../../api/engineering'
import { getUserSettings, putUserSettings } from '../../api/system'
import { downloadCsv } from '../../utils/reportExport'

const props = defineProps<{ catalog: EngineeringCatalog | null }>()

interface SavedQuery { id: string; name: string; text: string }

const editorRef = ref<HTMLTextAreaElement | null>(null)
const text = ref('SELECT Наименование, ИНН FROM Контрагенты\nLIMIT 10\n')
const running = ref(false)
const error = ref('')
const result = ref<QueryResult | null>(null)
const savedQueries = ref<SavedQuery[]>([])
const savedOpen = ref(false)

const resultColumns = computed<Column[]>(() =>
  (result.value?.columns ?? []).map((c) => ({ key: c.name, label: c.synonym || c.name })),
)

const numericTotals = computed(() => {
  const res = result.value
  if (!res || !res.rows.length) return []
  return res.columns
    .filter((c) => res.rows.some((r) => typeof r[c.name] === 'number'))
    .map((c) => {
      const vals = res.rows.map((r) => Number(r[c.name] ?? 0)).filter((v) => !Number.isNaN(v))
      const sum = vals.reduce((a, b) => a + b, 0)
      const avg = vals.length ? sum / vals.length : 0
      const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2))
      return { label: c.synonym || c.name, sum: fmt(sum), avg: fmt(avg) }
    })
})

function onSelectTable(_name: string) {
  /* выбор таблицы в дереве; реальная вставка — по клику на поле */
}

function insertToken(token: string) {
  const el = editorRef.value
  if (!el) {
    text.value += token
    return
  }
  const start = el.selectionStart ?? text.value.length
  const end = el.selectionEnd ?? text.value.length
  const needSpace = start > 0 && !/\s$/.test(text.value.slice(0, start))
  const insert = (needSpace ? ' ' : '') + token
  text.value = text.value.slice(0, start) + insert + text.value.slice(end)
  void nextTickFocus(el, start + insert.length)
}

function nextTickFocus(el: HTMLTextAreaElement, pos: number) {
  requestAnimationFrame(() => {
    el.focus()
    el.setSelectionRange(pos, pos)
  })
}

function onEditorKey(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'Enter') {
    e.preventDefault()
    void run()
  }
  if (e.key === 'Tab') {
    e.preventDefault()
    const el = e.target as HTMLTextAreaElement
    const start = el.selectionStart ?? text.value.length
    const end = el.selectionEnd ?? text.value.length
    text.value = text.value.slice(0, start) + '  ' + text.value.slice(end)
    nextTickFocus(el, start + 2)
  }
}

async function run() {
  if (!text.value.trim()) return
  running.value = true
  error.value = ''
  result.value = null
  try {
    const resp = await executeQuery(text.value, 1000)
    result.value = resp.data
  } catch (err) {
    const e = err as { message?: string }
    error.value = e.message || 'Ошибка выполнения запроса'
  } finally {
    running.value = false
  }
}

function clearEditor() {
  text.value = ''
  result.value = null
  error.value = ''
}

async function loadSavedQueries() {
  try {
    const resp = await getUserSettings('tables:console')
    const raw = resp.data?.saved_queries
    if (raw) savedQueries.value = JSON.parse(raw) as SavedQuery[]
  } catch {
    /* пусто */
  }
}

async function persistSaved() {
  try {
    await putUserSettings('tables:console', {
      saved_queries: JSON.stringify(savedQueries.value),
    })
  } catch {
    /* настройки опциональны */
  }
}

function saveCurrent() {
  if (!text.value.trim()) return
  const name = window.prompt('Имя запроса:', `Запрос ${savedQueries.value.length + 1}`)
  if (!name) return
  savedQueries.value = [
    ...savedQueries.value,
    { id: crypto.randomUUID(), name, text: text.value },
  ]
  void persistSaved()
}

function loadSaved(id: string) {
  const q = savedQueries.value.find((x) => x.id === id)
  if (q) text.value = q.text
  savedOpen.value = false
}

function deleteSaved(id: string) {
  savedQueries.value = savedQueries.value.filter((q) => q.id !== id)
  void persistSaved()
}

function printResult() {
  const res = result.value
  if (!res) return
  const win = window.open('', '_blank', 'width=1000,height=700')
  if (!win) return
  const headers = res.columns.map((c) => `<th>${escapeHtml(c.synonym || c.name)}</th>`).join('')
  const body = res.rows
    .map((r) => `<tr>${res.columns.map((c) => `<td>${escapeHtml(String(r[c.name] ?? ''))}</td>`).join('')}</tr>`)
    .join('')
  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Запрос</title>
  <style>body{font-family:sans-serif;padding:1rem}table{border-collapse:collapse;width:100%}th,td{border:1px solid #999;padding:4px 8px;font-size:12px}th{background:#f0f0f0}pre{background:#f5f5f5;padding:8px;border-radius:4px}</style>
  </head><body><pre>${escapeHtml(text.value)}</pre><table><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></body></html>`)
  win.document.close()
  win.focus()
  win.print()
}

function exportCsv() {
  const res = result.value
  if (!res) return
  const headers = res.columns.map((c) => c.synonym || c.name)
  const data = res.rows.map((r) => res.columns.map((c) => (r[c.name] as string | number | null) ?? ''))
  downloadCsv('query_result', headers, data)
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch] as string))
}

onMounted(loadSavedQueries)
</script>

<style scoped>
.console-split {
  grid-template-columns: 19rem 1fr;
}
.console-body {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  height: 100%;
  min-height: 0;
}
.console-toolbar {
  justify-content: flex-start;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.console-meta {
  margin-left: auto;
  font-size: 0.82rem;
}
.console-meta .trunc {
  color: var(--danger);
}
.console-editor {
  width: 100%;
  min-height: 9rem;
  flex: 0 0 auto;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9rem;
  line-height: 1.5;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg, #fff);
  color: var(--text);
  tab-size: 2;
}
.console-editor:focus {
  outline: none;
  border-color: var(--accent);
}
.console-error {
  color: var(--danger);
  font-size: 0.88rem;
  margin: 0;
  white-space: pre-wrap;
}
.console-result {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 0;
  flex: 1;
}
.console-totals {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.total-chip {
  font-size: 0.8rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: var(--bg-soft, #f0f0f0);
}
.console-result-actions {
  justify-content: flex-end;
  gap: 0.5rem;
}
.saved-wrap {
  position: relative;
}
.saved-menu {
  position: absolute;
  top: calc(100% + 0.3rem);
  left: 0;
  list-style: none;
  margin: 0;
  padding: 0.35rem;
  min-width: 220px;
  max-height: 320px;
  overflow: auto;
  z-index: 50;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}
.saved-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.saved-load {
  flex: 1;
  text-align: left;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
  border-radius: 6px;
}
.saved-load:hover {
  background: var(--bg-soft, #f5f5f5);
}
.saved-del {
  background: none;
  border: none;
  color: var(--danger);
  cursor: pointer;
  padding: 0.4rem 0.4rem;
  border-radius: 6px;
}
.saved-del:hover {
  background: var(--bg-soft, #f5f5f5);
}
@media (max-width: 900px) {
  .console-split {
    grid-template-columns: 1fr;
  }
  .eng-side {
    max-height: 16rem;
  }
}
</style>
