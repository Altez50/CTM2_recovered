import { computed, ref } from 'vue'

export type UiDensityMode = 'compact' | 'comfortable'

const STORAGE_KEY = 'ctm.uiDensity'
const LEGACY_STORAGE_KEY = 'ctm.documentDensity'
const densityMode = ref<UiDensityMode>('compact')

let initialized = false

function applyCompactDensity() {
  densityMode.value = 'compact'

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, 'compact')
    window.localStorage.setItem(LEGACY_STORAGE_KEY, 'compact')
  }

  if (typeof document !== 'undefined') {
    document.documentElement.classList.add('compact-ui')
  }
}

export function useUiDensity() {
  if (!initialized) {
    applyCompactDensity()
    initialized = true
  } else {
    applyCompactDensity()
  }

  const isCompactMode = computed(() => densityMode.value === 'compact')

  function toggleDensityMode() {
    applyCompactDensity()
  }

  function setDensityMode(_mode: UiDensityMode) {
    applyCompactDensity()
  }

  return {
    densityMode,
    isCompactMode,
    setDensityMode,
    toggleDensityMode,
  }
}
