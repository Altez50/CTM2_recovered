# Tabs Scroller Solutions

## Problem
Make `.tabs-scroller` use more free space within `.header-row` when child tabs don't fit.

## Current Behavior
- Horizontal scroll (`overflow-x: auto`)
- Tabs stay on single line

---

## Solution 1: Flex Wrap (Recommended)
Tabs wrap to multiple lines naturally.

```css
/* WorkspaceTabs.vue */
.tabs-scroller {
  display: flex;
  align-items: stretch;
  gap: 0.3rem;
  flex-wrap: wrap;           /* Enable wrapping */
  overflow-x: visible;       /* Disable horizontal scroll */
  align-content: flex-start; /* Stack rows from top */
  scrollbar-width: thin;
  scroll-behavior: smooth;
  min-width: 0;
  flex: 1 1 auto;
  padding-bottom: 0.15rem;
}

/* Optional: Limit to 2 rows with vertical scroll */
.tabs-scroller {
  max-height: calc(2 * 2.5rem); /* Adjust based on tab height */
  overflow-y: auto;
}
```

**Pros:** Accessible, responsive, no JS needed
**Cons:** Increases header height

---

## Solution 2: Scale Down (Zoom)
Scale tabs to fit container width.

```css
/* Requires JavaScript to detect overflow */
.tabs-scroller {
  display: flex;
  align-items: stretch;
  gap: 0.3rem;
  overflow: hidden; /* Prevent scroll */
  min-width: 0;
  flex: 1 1 auto;
}

/* Applied via JS when overflow detected */
.tabs-scroller.scaled {
  transform: scale(0.85);
  transform-origin: left center;
}
```

**JS Detection:**
```ts
const scroller = ref<HTMLElement | null>(null)
const tabs = ref<HTMLElement[]>([])

function checkOverflow() {
  if (!scroller.value) return
  const totalWidth = tabs.value.reduce((sum, tab) => sum + tab.offsetWidth, 0)
  const gaps = (tabs.value.length - 1) * 0.3 * 16 // 0.3rem in px
  const fits = totalWidth + gaps <= scroller.value.clientWidth
  scroller.value.classList.toggle('scaled', !fits)
}

// Call on resize, tab add/remove
```

**Pros:** Keeps single-line layout
**Cons:** Reduces readability, accessibility issues, complex

---

## Solution 3: Hybrid (Wrap + Max Height)
Wrap to 2 lines, then vertical scroll.

```css
.tabs-scroller {
  display: flex;
  align-items: stretch;
  gap: 0.3rem;
  flex-wrap: wrap;
  overflow-x: visible;
  overflow-y: auto;
  max-height: 5.5rem; /* ~2 tab rows + gaps */
  align-content: flex-start;
  min-width: 0;
  flex: 1 1 auto;
  padding-bottom: 0.15rem;
}
```

---

## Recommendation
**Implemented: Solution 4 (Progressive Shrinking)** — VS Code / Chrome style.

Tabs stay on a single line and shrink to `min-width` first; horizontal scroll
engages only after that threshold. Height of `header-row` never changes.

- `WorkspaceTabs.vue`: `.tab { flex: 0 1 auto; min-width: 6.5rem }`
  (compact: `5.5rem`), scrollbar kept thin (4px, unchanged).
- Wheel handler translates vertical wheel into horizontal scroll when overflow
  exists (`scrollWidth > clientWidth`), so the thin scrollbar stays discoverable.
- `tabs-menu` z-index raised + `.header { position: relative; z-index: 100 }` in
  `AppHeader.vue` to stop the dropdown being clipped by content below.

Superseded:
- Solution 1 (flex-wrap) — header height jumps on tab add/remove and resize.
- Solution 2 (scale/zoom) — readability & a11y regressions.

---

## Solution 4: Progressive Shrinking (Implemented)

Tabs shrink toward a `min-width` before any horizontal scroll kicks in.
One line always; layout height is stable.

```css
/* WorkspaceTabs.vue */
.tab {
  flex: 0 1 auto;     /* allow shrinking */
  min-width: 6.5rem;  /* threshold before scroll engages */
  max-width: 16rem;
}

.workspace-tabs.compact .tab {
  min-width: 5.5rem;
}

.tabs-menu { z-index: 200; } /* dropdown not clipped */
```

```ts
// Horizontal wheel scroll only when truly overflowing
function onWheel(event: WheelEvent) {
  const container = scrollerRef.value
  if (!container) return
  if (container.scrollWidth <= container.clientWidth) return
  event.preventDefault()
  container.scrollLeft += event.deltaY
}

onMounted(() => {
  scrollerRef.value?.addEventListener('wheel', onWheel, { passive: false })
})
```

**Pros:** Stable header height, all tabs visible as long as possible, no global
zoom, keeps existing `scrollIntoActive` watcher, accessible.
**Cons:** Tab labels truncate earlier (mitigated by existing `title` tooltip).