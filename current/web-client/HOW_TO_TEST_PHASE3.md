# How to Test Phase 3 - Quick Guide

## Prerequisites

### 1. Start the Servers
```bash
# Terminal 1: Start Backend API
python api/main.py

# Terminal 2: Start Frontend Dev Server
cd web-client
npm run dev
```

### 2. Verify Servers Running
- Backend: http://localhost:8000 (should show API info)
- Frontend: http://localhost:5173 (should show login page)
- API Docs: http://localhost:8000/docs (Swagger UI)

---

## Testing Methods

### Method 1: Interactive Test Tool (Recommended)

1. **Open the test tool**:
   - Navigate to: `web-client/test-phase3.html`
   - Or open: http://localhost:5173/../test-phase3.html

2. **Use viewport controls**:
   - Click buttons to switch between different screen sizes
   - Test mobile (375px, 414px), tablet (768px, 1024px), desktop (1280px, 1920px)

3. **Complete the checklist**:
   - Go through each section systematically
   - Check off items as you verify them
   - Track your progress in real-time

4. **Export results**:
   - Click "Export Test Results" when done
   - Save JSON file for documentation

### Method 2: Chrome DevTools

1. **Open the app**:
   ```
   http://localhost:5173
   ```

2. **Enable Device Toolbar**:
   - Press `Ctrl+Shift+M` (Windows/Linux)
   - Or `Cmd+Shift+M` (Mac)
   - Or click the device icon in DevTools

3. **Select devices**:
   - iPhone SE (375x667)
   - iPhone 12 Pro (414x896)
   - iPad (768x1024)
   - iPad Pro (1024x768)
   - Responsive mode (custom sizes)

4. **Test features**:
   - Navigation (hamburger menu)
   - Tables (card vs table view)
   - Forms (single vs multi-column)
   - Modals (full-screen vs centered)

---

## Test Scenarios

### Scenario 1: Mobile Navigation (5 minutes)

1. Set viewport to **375px** (iPhone SE)
2. Login to the app
3. Verify:
   - ✅ Sidebar is hidden
   - ✅ Hamburger menu button visible
4. Click hamburger menu
5. Verify:
   - ✅ Drawer slides in from left
   - ✅ Overlay appears
   - ✅ Animation is smooth
6. Click overlay
7. Verify:
   - ✅ Drawer closes
   - ✅ Overlay disappears
8. Open drawer again
9. Click a menu item
10. Verify:
    - ✅ Drawer closes automatically
    - ✅ Navigation works

**Expected Result**: All navigation features work smoothly on mobile

---

### Scenario 2: Mobile Table Views (10 minutes)

1. Set viewport to **375px**
2. Navigate to **Counterparties**
3. Verify:
   - ✅ Cards displayed (not table)
   - ✅ Each counterparty is a card
   - ✅ Key info visible
   - ✅ Cards are touch-friendly
4. Test search
5. Verify:
   - ✅ Search input full-width
   - ✅ Results update
6. Test pagination
7. Verify:
   - ✅ Mobile pagination buttons
   - ✅ "Назад" and "Вперед" buttons
8. Switch to **768px** (tablet)
9. Verify:
   - ✅ Table view appears
   - ✅ All columns visible
10. Repeat for other views:
    - Objects
    - Works
    - Persons
    - Organizations
    - Estimates
    - Daily Reports

**Expected Result**: Card layout on mobile, table on tablet/desktop

---

### Scenario 3: Mobile Form Creation (15 minutes)

1. Set viewport to **375px**
2. Navigate to **Counterparties**
3. Click **"Создать"** button
4. Verify:
   - ✅ Modal opens full-width
   - ✅ Form is single column
   - ✅ Inputs are full-width
   - ✅ Buttons are large
5. Fill in the form:
   - Name: "Test Counterparty Mobile"
   - Type: Select from dropdown
6. Verify:
   - ✅ Inputs work correctly
   - ✅ Validation works
7. Click **"Сохранить"**
8. Verify:
   - ✅ Saves successfully
   - ✅ Modal closes
   - ✅ New item appears in list

**Expected Result**: Form creation works smoothly on mobile

---

### Scenario 4: Mobile Estimate Creation (20 minutes)

1. Set viewport to **414px** (iPhone 12 Pro)
2. Navigate to **Estimates**
3. Click **"Создать"**
4. Verify:
   - ✅ Form opens
   - ✅ Single column layout
5. Fill header fields:
   - Number: "TEST-001"
   - Date: Select today
   - Customer: Use picker
   - Object: Use picker
6. Verify pickers:
   - ✅ Picker opens
   - ✅ Search works
   - ✅ Easy to select
7. Add estimate lines:
   - Click "Добавить строку"
   - Select work
   - Enter quantity: 10
   - Enter price: 1000
8. Verify:
   - ✅ Line added
   - ✅ Sum calculated (10,000)
   - ✅ Total updated
9. Add more lines
10. Verify:
    - ✅ Multiple lines work
    - ✅ Totals update
11. Click **"Сохранить"**
12. Verify:
    - ✅ Saves successfully

**Expected Result**: Estimate creation works on mobile with all features

---

### Scenario 5: Mobile Daily Report (20 minutes)

1. Set viewport to **375px**
2. Navigate to **Daily Reports**
3. Click **"Создать"**
4. Fill header:
   - Date: Today
   - Estimate: Select from picker
5. Verify:
   - ✅ Lines auto-filled from estimate
   - ✅ Planned labor shows
6. Enter actual labor:
   - First line: 8 hours
   - Second line: 6 hours
7. Verify:
   - ✅ Deviation calculated
   - ✅ Color-coded (green/red)
8. Select executors:
   - Click executor picker
   - Select multiple persons
9. Verify:
   - ✅ Multi-select works
   - ✅ Selected persons show
10. Click **"Сохранить"**
11. Verify:
    - ✅ Saves successfully

**Expected Result**: Daily report creation works on mobile

---

### Scenario 6: Tablet Testing (10 minutes)

1. Set viewport to **768px** (iPad)
2. Test all features:
   - Navigation (drawer still used)
   - Tables (table view, not cards)
   - Forms (2 columns)
   - Modals (centered, not full-screen)
3. Verify:
   - ✅ Everything works
   - ✅ Layout appropriate for tablet

**Expected Result**: Tablet experience is optimized

---

### Scenario 7: Desktop Testing (10 minutes)

1. Set viewport to **1280px**
2. Test all features:
   - Navigation (sidebar always visible)
   - Tables (full table view)
   - Forms (2-3 columns)
   - Modals (centered with max-width)
3. Verify:
   - ✅ Everything works
   - ✅ Layout appropriate for desktop

**Expected Result**: Desktop experience is optimal

---

### Scenario 8: Orientation Testing (5 minutes)

1. Test portrait mode:
   - 375x667 (iPhone portrait)
   - 768x1024 (iPad portrait)
2. Test landscape mode:
   - 667x375 (iPhone landscape)
   - 1024x768 (iPad landscape)
3. Verify:
   - ✅ Layout adapts
   - ✅ Everything accessible
   - ✅ No horizontal scroll

**Expected Result**: Works in both orientations

---

## Quick Checks

### ✅ Mobile Navigation
- [ ] Sidebar hidden on mobile
- [ ] Hamburger menu works
- [ ] Drawer opens/closes smoothly
- [ ] Overlay click closes drawer
- [ ] Menu items close drawer

### ✅ Mobile Tables
- [ ] Cards on mobile (<768px)
- [ ] Tables on tablet/desktop (≥768px)
- [ ] Search works
- [ ] Pagination works
- [ ] Touch-friendly

### ✅ Mobile Forms
- [ ] Single column on mobile
- [ ] Full-width inputs
- [ ] Large buttons
- [ ] Pickers work
- [ ] Validation works

### ✅ Mobile Modals
- [ ] Full-width on mobile
- [ ] Centered on desktop
- [ ] Close button accessible
- [ ] Backdrop click closes

### ✅ Performance
- [ ] Fast initial load
- [ ] Smooth animations
- [ ] No lag or jank
- [ ] Debounced search

---

## Common Issues & Solutions

### Issue: Sidebar not hiding on mobile
**Solution**: Check viewport width, should be <768px

### Issue: Cards not showing on mobile
**Solution**: Verify DataTable component is used, check responsive classes

### Issue: Forms not single column
**Solution**: Check grid classes, should be `grid-cols-1 md:grid-cols-2`

### Issue: Modals not full-screen
**Solution**: Check Modal component size prop and responsive classes

### Issue: Animations not smooth
**Solution**: Check CSS transitions, verify no JavaScript blocking

---

## Performance Testing

### Using Chrome DevTools:

1. **Open Performance tab**
2. **Start recording**
3. **Perform actions** (navigate, open forms, etc.)
4. **Stop recording**
5. **Analyze**:
   - Frame rate (should be 60fps)
   - Long tasks (should be minimal)
   - Layout shifts (should be none)

### Using Lighthouse:

1. **Open Lighthouse tab**
2. **Select**:
   - Mobile device
   - Performance category
3. **Run audit**
4. **Check scores**:
   - Performance: >90
   - Accessibility: >90
   - Best Practices: >90

### Network Throttling:

1. **Open Network tab**
2. **Select throttling**:
   - Fast 3G
   - Slow 3G
3. **Test app**:
   - Should still be usable
   - Loading states should show

---

## Reporting Issues

### If you find an issue:

1. **Document**:
   - What you were doing
   - What you expected
   - What actually happened
   - Viewport size
   - Browser/device

2. **Screenshot**:
   - Take screenshot of issue
   - Include DevTools if relevant

3. **Reproduce**:
   - Try to reproduce
   - Note steps to reproduce

4. **Report**:
   - Add to issues list
   - Include all details

---

## Completion Checklist

### Before marking Phase 3 complete:

- [ ] All test scenarios completed
- [ ] All viewports tested
- [ ] All user flows work
- [ ] No critical issues
- [ ] Performance acceptable
- [ ] Documentation updated
- [ ] Test results exported

---

## Tips for Efficient Testing

1. **Use keyboard shortcuts**:
   - `Ctrl+Shift+M` - Toggle device toolbar
   - `Ctrl+Shift+I` - Open DevTools
   - `F5` - Refresh page
   - `Ctrl+Shift+R` - Hard refresh

2. **Test systematically**:
   - One viewport at a time
   - One feature at a time
   - Check off items as you go

3. **Take notes**:
   - Document findings
   - Note any issues
   - Track progress

4. **Use the test tool**:
   - Provides structure
   - Tracks progress
   - Exports results

---

## Time Estimates

- **Quick Test** (all critical features): 30 minutes
- **Thorough Test** (all scenarios): 90 minutes
- **Complete Test** (all scenarios + performance): 2 hours

---

## Support

### If you need help:

1. Check documentation:
   - `PHASE3_TESTING.md`
   - `PHASE3_TEST_EXECUTION.md`
   - `PHASE3_COMPLETE.md`

2. Review code:
   - Component implementations
   - Responsive classes
   - TypeScript types

3. Check servers:
   - Backend running?
   - Frontend running?
   - Database accessible?

---

## Summary

Phase 3 testing is straightforward:
1. Start servers
2. Open test tool or use DevTools
3. Test different viewports
4. Verify all features work
5. Document results
6. Mark complete

**Good luck with testing!** 🚀

