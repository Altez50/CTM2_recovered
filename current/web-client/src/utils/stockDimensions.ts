import type { StockDimensions } from '../types/models'
export function stockDimensionsLabel(line: StockDimensions) {
  return [line.package_name ? `${line.package_name} · цена за упаковку · ${line.base_quantity ?? ''} базовых ед.` : '',
    line.characteristic_name, line.series_name].filter(Boolean).join(' · ')
}
