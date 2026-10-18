<template>
  <div class="goods-lines-editor">
    <div class="toolbar toolbar-wrap">
      <button class="button button-secondary" type="button" :disabled="disabled" @click="addLine">+ Добавить строку</button>
      <button class="button button-secondary" type="button" :disabled="disabled || !lines.length" @click="removeSelected">Удалить строку</button>
      <span v-if="totals" class="goods-lines-totals">
        Сумма без НДС: <strong>{{ formatMoney(totals.sum_without_vat) }}</strong>
        • НДС: <strong>{{ formatMoney(totals.vat_amount) }}</strong>
        • С НДС: <strong>{{ formatMoney(totals.sum_with_vat) }}</strong>
      </span>
    </div>

    <div class="goods-lines-table-shell">
      <table class="goods-lines-table">
        <thead>
          <tr>
            <th class="col-num">№</th>
            <th class="col-material">Материал</th>
            <th class="col-name">Наименование</th>
            <th>Упаковка и аналитики</th>
            <th class="col-unit">Ед.</th>
            <th class="col-num-val">Кол-во</th>
            <th class="col-num-val">Цена без НДС</th>
            <th class="col-num-val">НДС %</th>
            <th class="col-num-val">Сумма без НДС</th>
            <th class="col-num-val">Сумма с НДС</th>
            <th class="col-drawing">Чертёж</th>
            <th class="col-note">Примечание</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(line, index) in lines" :key="index" :class="{ selected: selectedIndex === index }" @click="selectedIndex = index">
            <td class="col-num">{{ index + 1 }}</td>
            <td class="col-material">
              <EntityPicker
                :model-value="line.material_id ?? null"
                :selected-label="line.material_code || (line.material_id ? line.name : '')"
                :disabled="disabled"
                compact
                title="Выбор материала"
                search-placeholder="Поиск материала…"
                :load-page="loadMaterials"
                edit-kind="materials"
                :detail-fields="['unit', 'price']"
                @update:model-value="(value) => onMaterialPick(index, value)"
                @change="(item) => onMaterialChange(index, item)"
              />
            </td>
            <td class="col-name">
              <input v-model="line.name" class="input inline-control" type="text" :disabled="disabled" placeholder="Наименование" />
            </td>
            <td><StockDimensionsEditor :line="line" :disabled="disabled" /></td>
            <td class="col-unit">
              <input v-model="line.unit" class="input inline-control" type="text" :disabled="disabled" placeholder="ед." />
            </td>
            <td class="col-num-val">
              <input v-model.number="line.quantity" class="input inline-control num" type="number" min="0" step="any" :disabled="disabled" @input="recompute(index)" />
            </td>
            <td class="col-num-val">
              <input v-model.number="line.price_without_vat" class="input inline-control num" type="number" min="0" step="any" :disabled="disabled" @input="recompute(index)" />
            </td>
            <td class="col-num-val">
              <input v-model.number="line.vat_rate" class="input inline-control num" type="number" min="0" max="100" step="any" :disabled="disabled" @input="recompute(index)" />
            </td>
            <td class="col-num-val num">{{ formatMoney(line.sum_without_vat) }}</td>
            <td class="col-num-val num">{{ formatMoney(line.sum_with_vat) }}</td>
            <td class="col-drawing">
              <input v-model="line.drawing_code" class="input inline-control" type="text" :disabled="disabled" />
            </td>
            <td class="col-note">
              <input v-model="line.note" class="input inline-control" type="text" :disabled="disabled" />
            </td>
          </tr>
          <tr v-if="!lines.length">
            <td colspan="12" class="empty">Нет строк. Нажмите «Добавить строку» или загрузите из Excel.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import EntityPicker from '../common/EntityPicker.vue'
import StockDimensionsEditor from './StockDimensionsEditor.vue'
import { listReferences } from '../../api/references'
import type { GoodsLine } from '../../types/models'

const props = defineProps<{
  lines: GoodsLine[]
  disabled?: boolean
  totals?: { sum_without_vat: number; vat_amount: number; sum_with_vat: number } | null
}>()
const emit = defineEmits<{ 'update:lines': [lines: GoodsLine[]] }>()

const selectedIndex = ref<number>(-1)

function formatMoney(value: number | undefined) {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0))
}

function notify() {
  emit('update:lines', [...props.lines])
}

function addLine() {
  props.lines.push({
    line_number: props.lines.length + 1,
    name: '',
    quantity: 0,
    price_without_vat: 0,
    vat_rate: 20,
    vat_amount: 0,
    sum_without_vat: 0,
    sum_with_vat: 0,
  })
  notify()
}

function removeSelected() {
  if (selectedIndex.value < 0) return
  props.lines.splice(selectedIndex.value, 1)
  if (selectedIndex.value >= props.lines.length) selectedIndex.value = props.lines.length - 1
  renumber()
  notify()
}

function renumber() {
  props.lines.forEach((l, i) => { l.line_number = i + 1 })
}

function recompute(index: number) {
  const line = props.lines[index]
  if (!line) return
  const qty = Math.max(0, Number(line.quantity) || 0)
  const price = Math.max(0, Number(line.price_without_vat) || 0)
  const rate = Math.max(0, Number(line.vat_rate) || 0)
  line.sum_without_vat = Math.round(qty * price * 100) / 100
  line.vat_amount = Math.round(line.sum_without_vat * rate) / 100
  line.sum_with_vat = Math.round((line.sum_without_vat + line.vat_amount) * 100) / 100
  notify()
}

async function loadMaterials(params: { search: string; page: number; pageSize: number }) {
  const res = await listReferences('materials', { search: params.search, page: params.page, page_size: params.pageSize })
  return {
    items: (res.data as unknown as Array<Record<string, unknown>>).filter((m) => !m.is_group).map((m) => ({
      id: m.id as number,
      label: `${String(m.code ?? '')} ${String(m.name ?? '')}`.trim(),
      caption: m.code ? `Код: ${m.code}` : undefined,
      meta: {
        unit: (m.unit_name ?? m.unit ?? '') as string,
        price: Number(m.price ?? 0),
        unit_id: m.unit_id,
      },
    })),
    pages: res.pagination?.pages ?? 1,
  }
}

function onMaterialPick(index: number, value: number | null) {
  const line = props.lines[index]
  if (!line) return
  line.material_id = value
  line.package_id = null; line.characteristic_id = null; line.series_id = null
  line.package_name = null; line.characteristic_name = null; line.series_name = null; line.conversion_factor = 1
  notify()
}

function onMaterialChange(index: number, item: { id?: number; label?: string; meta?: Record<string, unknown> } | null) {
  const line = props.lines[index]
  if (!line || !item) return
  if (!line.name && item.label) line.name = item.label
  if (item.meta) {
    line.unit_id = Number(item.meta.unit_id) || null
    if (item.meta.unit && !line.unit) line.unit = String(item.meta.unit)
    if (item.meta.price && !line.price_without_vat) line.price_without_vat = Number(item.meta.price)
  }
  notify()
}
</script>

<style scoped>
.goods-lines-editor { display: flex; flex-direction: column; gap: 0.5rem; }
.goods-lines-totals { margin-left: auto; font-size: 0.9rem; color: var(--muted, #666); }
.goods-lines-table-shell { overflow-x: auto; }
.goods-lines-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.goods-lines-table th, .goods-lines-table td { border: 1px solid var(--border, #ddd); padding: 0.25rem 0.35rem; vertical-align: middle; }
.goods-lines-table thead th { background: var(--panel-bg, #f5f5f5); font-weight: 600; text-align: center; }
.goods-lines-table tbody tr { cursor: pointer; }
.goods-lines-table tbody tr.selected { background: var(--accent-bg, #e6f0ff); }
.col-num { width: 2.5rem; text-align: center; }
.col-material { min-width: 160px; }
.col-name { min-width: 220px; }
.col-unit { width: 60px; }
.col-num-val { width: 110px; }
.col-drawing { min-width: 120px; }
.col-note { min-width: 140px; }
.inline-control { width: 100%; box-sizing: border-box; }
.num { text-align: right; }
.empty { text-align: center; color: var(--muted, #888); padding: 1rem; }
</style>
