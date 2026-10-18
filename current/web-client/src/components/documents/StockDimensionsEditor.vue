<template>
  <div class="stock-dimensions">
    <label>Упаковка
      <EntityPicker :model-value="line.package_id ?? null" :selected-label="line.package_name || ''" :disabled="disabled || !line.material_id"
        compact title="Упаковка товара" :load-page="pageLoader('material-packages')" edit-kind="material-packages"
        @update:model-value="value => line.package_id = value" @change="packageChanged" />
    </label>
    <label>Характеристика
      <EntityPicker :model-value="line.characteristic_id ?? null" :selected-label="line.characteristic_name || ''" :disabled="disabled || !line.material_id"
        compact title="Характеристика товара" :load-page="pageLoader('material-characteristics')" edit-kind="material-characteristics"
        @update:model-value="characteristicChanged" @change="item => line.characteristic_name = item?.label ?? null" />
    </label>
    <label>Серия
      <EntityPicker :model-value="line.series_id ?? null" :selected-label="line.series_name || ''" :disabled="disabled || !line.material_id"
        compact title="Серия товара" :load-page="pageLoader('material-series')" edit-kind="material-series"
        @update:model-value="value => line.series_id = value" @change="item => line.series_name = item?.label ?? null" />
    </label>
    <small>Базовое количество: {{ baseQty }}. {{ line.package_id ? 'Цена за упаковку.' : 'Цена за единицу строки.' }}</small>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import EntityPicker from '../common/EntityPicker.vue'
import { listReferences } from '../../api/references'
import type { MaterialAnalyticRecord, ReferenceKind, StockDimensions } from '../../types/models'
const props = defineProps<{ line: StockDimensions & { material_id?: number | null; quantity: number }; disabled?: boolean }>()
const baseQty = computed(() => Number((props.line.quantity * (props.line.conversion_factor ?? 1)).toFixed(6)))
function pageLoader(kind: ReferenceKind) {
  return async (params: { search: string; page: number; pageSize: number }) => {
    const response = await listReferences(kind, { search: params.search, page: params.page, page_size: params.pageSize,
      material_id: props.line.material_id ?? undefined,
      characteristic_id: kind === 'material-series' ? props.line.characteristic_id ?? undefined : undefined })
    return { items: (response.data as MaterialAnalyticRecord[]).map(item => ({ id: item.id, label: item.name,
      caption: item.factor ? `1 = ${item.factor} базовых единиц` : undefined, meta: { factor: item.factor ?? 1 } })), pages: response.pagination?.pages ?? 1 }
  }
}
function packageChanged(item: { label?: string; meta?: Record<string, unknown> } | null) {
  props.line.package_name = item?.label ?? null
  props.line.conversion_factor = Number(item?.meta?.factor ?? 1)
}
function characteristicChanged(value: number | null) {
  if (value !== props.line.characteristic_id) { props.line.series_id = null; props.line.series_name = null }
  props.line.characteristic_id = value
}
</script>
<style scoped>.stock-dimensions { min-width: 220px; display: grid; gap: .3rem; } small { color: var(--muted); }</style>
