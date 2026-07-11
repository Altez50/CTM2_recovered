import type { WorkRecord } from '../types/models'
import { listReferences } from './references'

let workCatalogCache: WorkRecord[] | null = null
let inflightCatalogRequest: Promise<WorkRecord[]> | null = null

function sortWorks(items: WorkRecord[]) {
  return [...items].sort((left, right) => {
    if (left.is_group !== right.is_group) {
      return left.is_group ? -1 : 1
    }

    const codeDiff = (left.code ?? '').localeCompare(right.code ?? '', 'ru', {
      numeric: true,
      sensitivity: 'base',
    })
    if (codeDiff !== 0) {
      return codeDiff
    }

    return left.name.localeCompare(right.name, 'ru', { numeric: true, sensitivity: 'base' })
  })
}

function dedupeWorks(items: WorkRecord[]) {
  const seen = new Set<number>()
  return sortWorks(
    items.filter((item) => {
      if (seen.has(item.id)) {
        return false
      }
      seen.add(item.id)
      return true
    }),
  )
}

export function clearWorkCatalogCache() {
  workCatalogCache = null
  inflightCatalogRequest = null
}

export async function loadWorkCatalog(force = false): Promise<WorkRecord[]> {
  if (!force && workCatalogCache) {
    return workCatalogCache
  }

  if (!force && inflightCatalogRequest) {
    return inflightCatalogRequest
  }

  inflightCatalogRequest = (async () => {
    const items: WorkRecord[] = []
    let page = 1
    let totalPages = 1

    while (page <= totalPages) {
      const response = await listReferences('works', {
        page,
        page_size: 50,
        sort_by: 'name',
        sort_order: 'asc',
      })

      items.push(...(response.data as WorkRecord[]))
      totalPages = response.pagination?.pages ?? page
      page += 1
    }

    workCatalogCache = dedupeWorks(items.filter((item) => !item.marked_for_deletion))
    return workCatalogCache
  })()

  try {
    return await inflightCatalogRequest
  } finally {
    inflightCatalogRequest = null
  }
}
