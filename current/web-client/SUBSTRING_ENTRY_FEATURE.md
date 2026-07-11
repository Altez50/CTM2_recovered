# Substring Entry Feature

## Overview

The Substring Entry feature enhances the user experience when selecting reference items (cost items, materials, units, and parent works) by providing real-time filtering and text highlighting based on user input.

## Features Implemented

### 1. Substring Matching Logic

**Requirements Validated:** 16.1, 16.2

The system searches both the `code` and `name` fields of items:
- **Case-insensitive matching**: "цем" matches "Цемент М400"
- **Partial matching**: "M00" matches "M001", "M002", "M003"
- **Multi-field search**: Searches in both code and description/name fields simultaneously

**Implementation:**
```typescript
const filteredItems = computed(() => {
  const query = searchQuery.value.toLowerCase().trim()
  
  if (!query) {
    return props.items
  }

  return props.items.filter(item => {
    const code = props.getItemCode(item).toLowerCase()
    const description = props.getItemDescription(item).toLowerCase()
    return code.includes(query) || description.includes(query)
  })
})
```

### 2. Real-time Filtering

**Requirements Validated:** 16.2

As the user types in the search field, the list updates immediately:
- No delay or debouncing required for small datasets
- Instant visual feedback
- Result count updates dynamically

### 3. Enter Key Selection

**Requirements Validated:** 16.3

Pressing Enter automatically selects the first matching item:
- Only selects if items are available
- Skips disabled items
- Automatically confirms selection and closes dialog

**Implementation:**
```typescript
function handleEnterKey() {
  if (displayedItems.value.length > 0) {
    const firstItem = displayedItems.value[0]
    if (!isDisabled(firstItem)) {
      selectItem(firstItem)
      confirm()
    }
  }
}
```

### 4. Text Highlighting

**Requirements Validated:** 16.4

Matching text is highlighted with a yellow background:
- Uses `<mark>` HTML tags for semantic highlighting
- Escapes special regex characters to prevent errors
- Highlights all occurrences of the search term
- Works in both code and description fields

**Visual Example:**
```
Search: "цем"
Result: Цемент М400 → <mark>Цем</mark>ент М400
```

**Implementation:**
```typescript
function highlightText(text: string): string {
  if (!props.highlightMatches || !searchQuery.value.trim()) {
    return text
  }
  
  const query = searchQuery.value.trim()
  const regex = new RegExp(`(${escapeRegex(query)})`, 'gi')
  return text.replace(regex, '<mark>$1</mark>')
}
```

**CSS Styling:**
```css
:deep(mark) {
  background-color: #fff3cd;
  color: #856404;
  padding: 0.1rem 0.2rem;
  border-radius: 0.2rem;
  font-weight: 600;
}
```

### 5. Clear Search

**Requirements Validated:** 16.5

Clearing the search field shows the full unfiltered list:
- Automatically handled by Vue's v-model binding
- No special logic required
- Instant restoration of full list

## Components Updated

### Base Component: ListForm.vue

The base `ListForm` component now includes:
- `highlightMatches` prop (default: true)
- `highlightText()` function exposed to child components
- Enhanced template with v-html for highlighted text
- Regex escaping for safe text replacement

### Specialized Components

All specialized list forms now use the highlighting feature:

1. **CostItemListForm.vue**
   - Highlights code and description
   - Works with hierarchical items

2. **MaterialListForm.vue**
   - Highlights code and description
   - Works with unit filtering

3. **UnitListForm.vue**
   - Highlights name and description
   - Simple flat list

4. **WorkListForm.vue**
   - Highlights code and name
   - Works with hierarchical structure
   - Maintains hierarchy path display

## Usage Examples

### Example 1: Finding Materials by Code
```
User types: "M00"
Results shown:
  - M001 - Цемент М400
  - M002 - Песок речной
  - M003 - Щебень фракция 5-20
```

### Example 2: Finding Materials by Name
```
User types: "цем"
Results shown:
  - M001 - Цемент М400
  - M005 - Портландцемент М500
```

### Example 3: Quick Selection
```
User types: "M001"
User presses: Enter
Result: Material M001 is selected and dialog closes
```

### Example 4: Cyrillic Search
```
User types: "труд"
Results shown:
  - C001 - Труд рабочих
  - C004 - Труд машинистов
```

## Testing

### Unit Tests

Comprehensive test suite in `ListForm.spec.ts`:

✅ Filter items by code substring
✅ Filter items by name substring
✅ Filter items by description substring
✅ Case-insensitive matching
✅ Text highlighting when enabled
✅ Enter key selection
✅ Clear search shows all items
✅ Empty state when no matches
✅ Filter by both code and name
✅ Escape special regex characters
✅ No highlighting when search is empty
✅ No highlighting when disabled

**Test Results:**
```
✓ 12 tests passed
✓ Duration: 90ms
```

## Performance Considerations

### Current Implementation
- **Client-side filtering**: All filtering happens in the browser
- **No debouncing**: Instant updates for better UX
- **Suitable for**: Lists up to ~1000 items

### Future Optimizations (if needed)
- Server-side filtering for very large datasets
- Debouncing for slow connections
- Virtual scrolling for long result lists

## Browser Compatibility

- ✅ Modern browsers (Chrome, Firefox, Safari, Edge)
- ✅ Supports Unicode (Cyrillic, Latin, etc.)
- ✅ Accessible (uses semantic HTML)

## Accessibility

- Search input has proper labels
- Keyboard navigation supported (Tab, Enter, Escape)
- Screen reader friendly (semantic HTML with `<mark>`)
- Visual indicators for matches

## Known Limitations

1. **Special Characters**: Some special regex characters need escaping (handled automatically)
2. **Performance**: Very large lists (>5000 items) may benefit from server-side filtering
3. **Highlighting**: Only works with text content, not with complex HTML structures

## Future Enhancements

Potential improvements for future versions:
- Fuzzy matching (typo tolerance)
- Search history
- Recent selections
- Keyboard shortcuts (Ctrl+F to focus search)
- Advanced filters (AND/OR logic)
- Search by multiple fields with weights

## Related Requirements

This feature validates the following requirements from the design document:

- **Requirement 16.1**: Substring matching against code and name fields
- **Requirement 16.2**: Real-time filtering as user types
- **Requirement 16.3**: Enter key selects first match
- **Requirement 16.4**: Multiple matches with highlighted text
- **Requirement 16.5**: Clear search shows full list

## Correctness Properties

This feature implements the following correctness properties:

- **Property 44**: Substring filtering by code or name
- **Property 45**: Enter key selects first match
- **Property 47**: Clear search shows full list
