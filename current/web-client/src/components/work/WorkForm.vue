<template>
  <Modal
    :open="open"
    size="full"
    :title="work.id ? (work.is_group ? 'Карточка группы' : 'Карточка работы') : 'Новая работа'"
    :hide-header="true"
    @close="requestClose"
  >
    <div class="work-form">
      <div class="work-topbar">
        <div class="work-topbar-main">
          <div>
            <h2 class="work-card-title">{{ work.id ? (work.is_group ? 'Карточка группы' : 'Карточка работы') : 'Новая работа' }}</h2>
          </div>
          <span class="status-pill" :class="dirty ? 'draft' : 'posted'">
            {{ dirty ? 'Есть изменения' : 'Сохранено' }}
          </span>
        </div>

        <div class="work-topbar-actions">
          <button
            class="button button-secondary work-icon-button"
            type="button"
            title="Закрыть карточку"
            aria-label="Закрыть карточку"
            @click="requestClose"
          >
            ×
          </button>
          <button
            class="button button-secondary work-icon-button"
            type="button"
            :disabled="loading"
            title="Отменить несохраненные изменения"
            aria-label="Отменить несохраненные изменения"
            @click="cancelEdits"
          >
            ↶
          </button>
          <button
            class="button button-primary work-icon-button work-icon-button-primary"
            type="button"
            :disabled="loading || saving"
            :title="saving ? 'Сохраняем карточку' : 'Сохранить карточку'"
            aria-label="Сохранить карточку"
            @click="saveWork"
          >
            ✓
          </button>
        </div>
      </div>

      <div v-if="loading" class="panel panel-body centered-state">
        Загружаем карточку работы…
      </div>

      <template v-else>
        <section class="panel work-main-panel">
          <button class="work-section-toggle" type="button" @click="toggleMainSection">
            <span class="work-section-toggle-main">
              <span class="work-section-toggle-icon">{{ mainSectionCollapsed ? '▶' : '▼' }}</span>
              <span class="section-title">Основные реквизиты</span>
            </span>
            <span class="work-section-toggle-state">
              {{ mainSectionCollapsed ? 'Свернуто' : 'Развернуто' }}
            </span>
          </button>

          <div v-if="!mainSectionCollapsed" class="panel-body panel-stack work-main-panel-body">

            <div v-if="errorMessage" class="message-banner message-error">
              {{ errorMessage }}
            </div>

            <div v-if="saveMessage" class="message-banner message-success">
              {{ saveMessage }}
            </div>

            <div v-if="laborWarning" class="message-banner message-warning">
              {{ laborWarning }}
            </div>

            <div class="work-basic-grid">
              <FormField class="work-field-span-4" label="Наименование" :error="fieldErrors.name">
                <input
                  :value="work.name"
                  class="input work-compact-control work-flat-control"
                  type="text"
                  placeholder="Например, Штукатурка стен"
                  @input="handleWorkTextInput('name', $event)"
                />
              </FormField>

              <FormField class="work-field-span-1" label="Код">
                <input
                  :value="work.code"
                  class="input work-compact-control work-flat-control"
                  type="text"
                  placeholder="Внутренний код работы"
                  @input="handleWorkTextInput('code', $event)"
                />
              </FormField>

              <FormField class="work-field-span-1" label="Единица измерения">
                <input
                  :value="work.unit"
                  class="input work-compact-control work-flat-control"
                  type="text"
                  list="work-unit-options"
                  placeholder="м², м³, шт"
                  @input="handleWorkTextInput('unit', $event)"
                />
                <datalist id="work-unit-options">
                  <option v-for="unit in units" :key="unit.id" :value="unit.short_name || unit.name">
                    {{ unit.name }}
                  </option>
                </datalist>
              </FormField>

              <FormField class="work-field-span-2" label="Родительская группа">
                <select :value="work.parent_id ?? ''" class="select work-compact-control work-flat-control" @change="handleParentChange">
                  <option value="">Без родителя</option>
                  <option v-for="option in groupOptions" :key="option.id" :value="option.id">
                    {{ option.label }}
                  </option>
                </select>
              </FormField>

              <FormField class="work-field-span-2 work-checkbox-field" label="Тип записи">
                <label class="checkbox-row">
                  <input :checked="work.is_group" type="checkbox" @change="handleGroupToggle" />
                  <span>Это групповой элемент</span>
                </label>
              </FormField>

              <FormField v-if="!work.is_group" class="work-field-span-1" label="Норма труда" :error="fieldErrors.labor_rate">
                <input
                  :value="formatNumericInput(work.labor_rate)"
                  class="input work-compact-control work-flat-control work-number-control"
                    type="number"
                    min="0"
                    step="0.0001"
                  @change="handleWorkNumberChange('labor_rate', $event)"
                />
              </FormField>

              <FormField v-if="!work.is_group" class="work-field-span-1" label="Цена" :error="fieldErrors.price">
                <input
                  :value="formatNumericInput(work.price)"
                  class="input work-compact-control work-flat-control work-number-control"
                    type="number"
                    min="0"
                    step="0.01"
                  @change="handleWorkNumberChange('price', $event)"
                />
              </FormField>
            </div>

            <div v-if="specificationReviewEnabled" class="work-review-card">
              <div class="work-review-head">
                <strong>Проверка спецификации</strong>
              </div>

              <div class="work-review-grid">
                <FormField label="Статус проверки спецификации">
                  <select
                    :value="work.specification_review_status"
                    class="select work-compact-control work-flat-control"
                    @change="handleReviewStatusChange"
                  >
                    <option v-for="option in reviewStatusOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </FormField>

                <FormField label="Комментарий проверки">
                  <input
                    :value="work.specification_review_note"
                    class="input work-compact-control work-flat-control"
                    type="text"
                    placeholder="Например, проверить импортированные материалы"
                    @input="handleReviewNoteInput"
                  />
                </FormField>
              </div>
            </div>

            <div v-if="work.is_group && hasHiddenGroupValues" class="message-banner message-warning">
              Для групповой работы цена и норма труда должны быть равны нулю.
              <button class="button button-secondary inline-button" type="button" @click="clearGroupValues">
                Обнулить скрытые значения
              </button>
            </div>

            <div
              v-if="specificationReviewEnabled && work.specification_review_status === 'incorrect'"
              class="message-banner message-warning"
            >
              Спецификация помечена как требующая исправления. Ее можно выгрузить из каталога работ и
              вернуть через импорт исправлений.
            </div>

            <div v-if="fieldErrors.group" class="message-banner message-error">
              {{ fieldErrors.group }}
            </div>
          </div>
        </section>

        <section class="panel specification-panel">
          <button class="specification-header" type="button" @click="toggleCollapsed">
            <span class="specification-header-main">
              <span class="specification-toggle">{{ collapsed ? '▶' : '▼' }}</span>
              <span>
                <strong>Спецификация</strong>
                <span v-if="!collapsed" class="specification-caption">
                  {{ summaryCaption }}
                </span>
              </span>
            </span>
            <span class="specification-total">{{ formatMoney(overallTotal) }}</span>
          </button>

          <div v-if="!collapsed" class="panel-body specification-body">
            <div class="toolbar toolbar-wrap specification-toolbar">
              <input
                v-model="searchInput"
                class="input toolbar-grow specification-toolbar-control work-flat-control"
                type="search"
                placeholder="Поиск по наименованию компонента"
              />

              <select v-model="typeFilter" class="select filter-select specification-toolbar-control work-flat-control">
                <option value="All">Все типы</option>
                <option v-for="option in componentTypeOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>

              <button class="button button-secondary specification-toolbar-button" type="button" @click="addRow">
                Добавить строку
              </button>
              <button class="button button-secondary specification-toolbar-button" type="button" title="Копировать из работы" @click="openCopyModal">
                ⎘
              </button>
              <button class="button button-secondary specification-toolbar-button" type="button" @click="triggerImport">
                Импорт
              </button>
              <button class="button button-secondary specification-toolbar-button" type="button" @click="exportCurrentSpecification">
                Экспорт
              </button>
            </div>

            <input
              ref="importInputRef"
              class="visually-hidden"
              type="file"
              accept=".xls,.xlsx"
              @change="handleImportFile"
            />

            <datalist id="component-name-options">
              <option v-for="name in componentNameSuggestions" :key="name" :value="name" />
            </datalist>
            <datalist id="specification-unit-options">
              <option v-for="unit in units" :key="unit.id" :value="unit.short_name || unit.name">
                {{ unit.name }}
              </option>
            </datalist>

            <div v-if="specifications.length === 0" class="empty-specification specification-empty">
              Спецификация пока пуста. Добавьте строку, импортируйте Excel или скопируйте состав из
              другой работы.
            </div>

            <div v-else-if="visibleSpecifications.length === 0" class="empty-specification specification-empty">
              Фильтры не вернули строк. Сбросьте поиск или тип компонента.
            </div>

            <div v-else class="specification-table-shell">
              <table class="specification-table">
                <colgroup>
                  <col class="specification-col-type" />
                  <col class="specification-col-name" />
                  <col class="specification-col-unit" />
                  <col class="specification-col-rate" />
                  <col class="specification-col-price" />
                  <col class="specification-col-total" />
                  <col class="specification-col-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Тип</th>
                    <th>Наименование</th>
                    <th>Ед. изм.</th>
                    <th>Норма</th>
                    <th>Цена</th>
                    <th>Сумма</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="row in visibleSpecifications" :key="row.localId">
                    <tr>
                      <td class="spec-cell-type">
                        <select :value="row.component_type" class="select inline-control work-flat-control" @change="updateRowType(row, $event)">
                          <option v-for="option in componentTypeOptions" :key="option.value" :value="option.value">
                            {{ option.label }}
                          </option>
                        </select>
                      </td>

                      <td class="spec-cell-name">
                        <div class="name-cell">
                          <div :class="['name-field-control', { 'name-field-control-material': usesMaterialCatalog(row.component_type) }]">
                            <input
                              :value="row.component_name"
                              class="input inline-control work-flat-control name-field-input"
                              type="text"
                              list="component-name-options"
                              placeholder="Наименование компонента"
                              @input="updateRowText(row, 'component_name', $event)"
                            />

                            <button
                              v-if="usesMaterialCatalog(row.component_type)"
                              class="button button-secondary material-picker-button"
                              type="button"
                              title="Подобрать из справочника материалов"
                              aria-label="Подобрать из справочника материалов"
                              @click="openMaterialModal(row, row.component_name)"
                            >
                              ...
                            </button>
                          </div>

                          <span v-if="usesMaterialCatalog(row.component_type) && row.material_id" class="field-hint">
                            Связано со справочником материалов
                          </span>
                        </div>
                      </td>

                      <td class="spec-cell-unit">
                        <input
                          :value="row.unit_name ?? ''"
                          class="input inline-control work-flat-control"
                          type="text"
                          list="specification-unit-options"
                          placeholder="Ед. изм."
                          @input="updateRowUnit(row, $event)"
                        />
                      </td>

                      <td class="spec-cell-number">
                        <input
                          :value="formatNumericInput(row.consumption_rate)"
                          class="input inline-control work-flat-control"
                          type="number"
                          min="0.0001"
                          step="0.0001"
                          @change="handleRowNumberChange(row, 'consumption_rate', $event)"
                        />
                      </td>

                      <td class="spec-cell-number">
                        <input
                          :value="formatNumericInput(row.unit_price)"
                          class="input inline-control work-flat-control"
                          type="number"
                          min="0"
                          step="0.01"
                          @change="handleRowNumberChange(row, 'unit_price', $event)"
                        />
                      </td>

                      <td class="spec-cell-total">
                        <span class="row-total">{{ formatMoney(row.total_cost) }}</span>
                      </td>

                      <td class="spec-cell-actions">
                        <div class="table-actions">
                          <button
                            class="button button-danger row-delete-button"
                            type="button"
                            title="Удалить строку"
                            aria-label="Удалить строку"
                            @click="removeRow(row.localId)"
                          >
                            ×
                          </button>
                        </div>
                      </td>
                    </tr>

                    <tr v-if="shouldShowRowErrors(row)" class="row-error-strip">
                      <td colspan="7">
                        {{ rowMessages(row).join(' • ') }}
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>

            <div class="totals-panel specification-totals">
              <div class="totals-header">
                <h3>Итоги</h3>
                <span class="muted">{{ summaryCaption }}</span>
              </div>

              <div class="totals-grid">
                <div v-for="item in visibleSubtotals" :key="item.type" class="total-card">
                  <span class="muted">{{ item.label }}</span>
                  <strong>{{ formatMoney(item.total) }}</strong>
                </div>
                <div class="total-card total-card-strong">
                  <span class="muted">Общая стоимость</span>
                  <strong>{{ formatMoney(visibleTotal) }}</strong>
                </div>
              </div>
            </div>
          </div>
        </section>

      </template>
    </div>

    <Modal
      :open="copyModalOpen"
      title="Копирование из другой работы"
      description="Выберите работу-источник и просмотрите строки до подтверждения."
      @close="closeCopyModal"
    >
      <div class="modal-stack">
        <input
          v-model="copySearch"
          class="input"
          type="search"
          placeholder="Поиск работы-источника"
        />

        <div v-if="copyError" class="message-banner message-error">
          {{ copyError }}
        </div>

        <div class="copy-layout">
          <div class="copy-list">
            <button
              v-for="item in copySourceOptions"
              :key="item.id"
              class="copy-source"
              :class="{ selected: item.id === selectedCopySourceId }"
              type="button"
              @click="selectCopySource(item.id)"
            >
              <strong>{{ item.name }}</strong>
              <span class="muted">{{ item.code || 'Без кода' }}</span>
            </button>
            <div v-if="copySourceOptions.length === 0" class="empty-specification">
              Подходящих работ не найдено.
            </div>
          </div>

          <div class="copy-preview">
            <div v-if="copyPreviewLoading" class="empty-specification">Загружаем состав работы…</div>
            <div v-else-if="copyPreviewRows.length === 0" class="empty-specification">
              Выберите работу слева, чтобы просмотреть строки спецификации.
            </div>
            <div v-else class="preview-table-shell">
              <table class="preview-table">
                <thead>
                  <tr>
                    <th>Тип</th>
                    <th>Наименование</th>
                    <th>Ед. изм.</th>
                    <th>Норма</th>
                    <th>Цена</th>
                    <th>Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in copyPreviewRows" :key="row.id ?? `${selectedCopySourceId}-${index}`">
                    <td>{{ componentTypeLabel(row.component_type) }}</td>
                    <td>{{ row.component_name }}</td>
                    <td>{{ row.unit_name || '—' }}</td>
                    <td>{{ formatNumber(row.consumption_rate) }}</td>
                    <td>{{ formatMoney(row.unit_price) }}</td>
                    <td>{{ formatMoney(row.total_cost) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="toolbar">
          <button
            class="button button-primary"
            type="button"
            :disabled="copyPreviewRows.length === 0"
            @click="applyCopyPreview"
          >
            Добавить строки
          </button>
          <button class="button button-secondary" type="button" @click="closeCopyModal">Отмена</button>
        </div>
      </div>
    </Modal>

    <Modal
      :open="importModalOpen"
      size="full"
      title="Импорт спецификации из Excel"
      description="Проверьте строки, исправьте ошибки при необходимости и добавьте корректные записи в карточку."
      @close="closeImportModal"
    >
      <div class="modal-stack">
        <div v-if="importError" class="message-banner message-error">
          {{ importError }}
        </div>
        <div v-if="importMessage" class="message-banner message-success">
          {{ importMessage }}
        </div>

        <div class="toolbar">
          <span class="muted">
            {{ importFileName ? `Файл: ${importFileName}` : 'Файл ещё не выбран' }}
          </span>
          <button class="button button-secondary" type="button" @click="triggerImport">
            Выбрать другой файл
          </button>
        </div>

        <!-- NEW: Unit Summary Section -->
        <div v-if="importRows.length > 0" class="unit-summary">
          <h4>Единицы измерения</h4>
          <div class="unit-stats">
            <span class="stat">
              <strong>{{ importUnitStats.existingCount }}</strong> существующих
            </span>
            <span v-if="importUnitStats.newCount > 0" class="stat stat-warning">
              <strong>{{ importUnitStats.newCount }}</strong> будут созданы
            </span>
          </div>
          
          <!-- NEW: New units warning -->
          <div v-if="importUnitStats.uniqueNewUnits.length > 0" class="new-units-warning">
            <p class="warning-text">⚠️ Будут созданы новые единицы измерения:</p>
            <ul class="new-units-list">
              <li v-for="unit in importUnitStats.uniqueNewUnits" :key="unit">
                "{{ unit }}"
              </li>
            </ul>
            <p class="hint-text">
              Если единица уже существует, проверьте написание в Excel файле
            </p>
          </div>
        </div>

        <div v-if="missingImportMaterials.length > 0" class="unit-summary">
          <h4>Новые материалы</h4>
          <div class="unit-stats">
            <span class="stat stat-warning">
              <strong>{{ missingImportMaterials.length }}</strong> будут созданы в справочнике
            </span>
          </div>
          <div class="missing-materials-list">
            <div v-for="material in missingImportMaterials" :key="`${material.material_code || material.material_name}`" class="missing-material-item">
              <div>
                <strong>{{ material.material_name }}</strong>
                <div class="muted">
                  {{ material.material_code ? `Код: ${material.material_code}` : 'Без кода' }}
                </div>
                <div class="muted">
                  Строки: {{ material.source_row_numbers.join(', ') }}
                </div>
              </div>
              <div class="material-meta-inline">
                <span>{{ material.unit_name || '—' }}</span>
                <strong>{{ formatMoney(material.unit_price) }}</strong>
              </div>
            </div>
          </div>
          <div class="toolbar">
            <button
              class="button button-primary"
              type="button"
              :disabled="creatingImportMaterials"
              @click="createMissingImportMaterials"
            >
              {{ creatingImportMaterials ? 'Создание материалов…' : 'Создать материалы из файла' }}
            </button>
          </div>
        </div>

        <div v-if="importRows.length === 0" class="empty-specification">
          После выбора файла здесь появится предварительный просмотр строк.
        </div>

        <div v-else class="preview-table-shell">
          <datalist id="import-unit-options">
            <option v-for="unit in units" :key="`import-${unit.id}`" :value="unit.short_name || unit.name">
              {{ unit.name }}
            </option>
          </datalist>

          <table class="preview-table">
            <thead>
              <tr>
                <th>Строка</th>
                <th>Тип</th>
                <th>Наименование</th>
                <th>Ед. изм.</th>
                <th>Норма</th>
                <th>Цена</th>
                <th>Сумма</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in importRows" :key="row.id">
                <td>{{ row.source_row }}</td>
                <td>
                  <select :value="row.component_type" class="select inline-control" @change="updateImportType(row, $event)">
                    <option value="">Выберите</option>
                    <option v-for="option in componentTypeOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </td>
                <td>
                  <input
                    :value="row.component_name"
                    class="input inline-control"
                    type="text"
                    @input="updateImportText(row, 'component_name', $event)"
                  />
                  <div v-if="row.material_code || row.matched_material_name" class="field-hint">
                    <span v-if="row.material_code">Код: {{ row.material_code }}</span>
                    <span v-if="row.material_code && row.matched_material_name"> · </span>
                    <span v-if="row.matched_material_name">Справочник: {{ row.matched_material_name }}</span>
                  </div>
                </td>
                <td>
                  <div class="unit-cell">
                    <input
                      :value="row.unit_name"
                      class="input inline-control"
                      type="text"
                      list="import-unit-options"
                      @input="updateImportText(row, 'unit_name', $event)"
                    />
                    <!-- NEW: Unit status badge -->
                    <span 
                      v-if="row.unit_status === 'new'" 
                      class="badge badge-warning"
                      title="Будет создана новая единица"
                    >
                      новая
                    </span>
                    <span 
                      v-else-if="row.unit_status === 'existing'" 
                      class="badge badge-success"
                      :title="`Существующая единица (ID ${row.unit_id})`"
                    >
                      ID {{ row.unit_id }}
                    </span>
                  </div>
                </td>
                <td>
                  <input
                    :value="row.consumption_rate"
                    class="input inline-control"
                    type="text"
                    @input="updateImportText(row, 'consumption_rate', $event)"
                  />
                </td>
                <td>
                  <input
                    :value="row.unit_price"
                    class="input inline-control"
                    type="text"
                    @input="updateImportText(row, 'unit_price', $event)"
                  />
                </td>
                <td>{{ formatMoney(importRowTotal(row)) }}</td>
                <td>
                  <div class="status-cell">
                    <span v-if="importRowErrors(row).length" class="error-list">
                      {{ importRowErrors(row).join(' • ') }}
                    </span>
                    <span
                      v-else-if="usesMaterialCatalog(row.component_type) && row.material_status === 'existing'"
                      class="success-text"
                    >
                      Найдено в справочнике материалов
                    </span>
                    <span
                      v-else-if="usesMaterialCatalog(row.component_type) && row.material_status === 'new'"
                      class="warning-text-inline"
                    >
                      Требуется создание материала
                    </span>
                    <span v-else-if="!row.warnings || row.warnings.length === 0" class="success-text">
                      Готово к импорту
                    </span>
                    <span v-else class="success-text">
                      Готово к импорту
                    </span>
                    <ul v-if="row.warnings && row.warnings.length > 0" class="warning-list">
                      <li v-for="(warning, idx) in row.warnings" :key="idx" class="warning-item">
                        ⚠️ {{ warning }}
                      </li>
                    </ul>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="toolbar">
          <button
            class="button button-primary"
            type="button"
            :disabled="validImportRows.length === 0"
            @click="applyImportRows('append')"
          >
            Добавить {{ validImportRows.length }} строк
          </button>
          <button
            class="button button-secondary"
            type="button"
            :disabled="validImportRows.length === 0"
            @click="applyImportRows('replace')"
          >
            Заменить спецификацию
          </button>
          <button class="button button-secondary" type="button" @click="closeImportModal">Отмена</button>
        </div>
      </div>
    </Modal>

    <Modal
      :open="materialModalOpen"
      title="Выбор материала"
      description="Материал автоматически заполнит наименование, единицу измерения и цену."
      @close="closeMaterialModal"
    >
      <div class="modal-stack">
        <div class="toolbar">
          <input
            v-model="materialSearch"
            class="input toolbar-grow"
            type="search"
            placeholder="Поиск по наименованию или коду"
          />
          <button class="button button-secondary" type="button" title="Обновить" @click="loadMaterials">
            ↻
          </button>
        </div>

        <div v-if="materialError" class="message-banner message-error">
          {{ materialError }}
        </div>

        <div v-if="materialLoading" class="empty-specification">
          Загружаем каталог материалов…
        </div>

        <div v-else-if="materials.length === 0" class="empty-specification">
          Материалы не найдены.
        </div>

        <div v-else class="material-list">
          <div
            v-for="material in materials"
            :key="material.id"
            class="material-item-row"
          >
            <button
              v-if="editingMaterialId !== material.id"
              class="material-item"
              type="button"
              @click="applyMaterial(material)"
            >
              <span>
                <strong>{{ material.name }}</strong>
                <span class="muted">{{ material.code || 'Без кода' }}</span>
              </span>
              <span class="material-meta">
                <span>{{ material.unit_name || '—' }}</span>
                <strong>{{ formatMoney(material.price) }}</strong>
              </span>
            </button>
            <button
              v-if="editingMaterialId !== material.id"
              class="button button-secondary material-edit-button"
              type="button"
              title="Изменить"
              @click.stop="startEditMaterial(material)"
            >
              Изм.
            </button>
            <div v-if="editingMaterialId === material.id" class="material-edit-form">
              <input
                v-model="editingMaterial.name"
                class="input"
                type="text"
                placeholder="Наименование"
              />
              <input
                v-model="editingMaterial.code"
                class="input"
                type="text"
                placeholder="Код"
              />
              <input
                v-model="editingMaterial.unit_name"
                class="input"
                type="text"
                placeholder="Ед. изм."
              />
              <input
                v-model.number="editingMaterial.price"
                class="input"
                type="number"
                step="0.01"
                placeholder="Цена"
              />
              <button
                class="button button-primary"
                type="button"
                :disabled="savingMaterial"
                @click="saveEditedMaterial"
              >
                {{ savingMaterial ? '…' : 'OK' }}
              </button>
              <button
                class="button button-secondary"
                type="button"
                @click="cancelEditMaterial"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>

        <div class="toolbar pagination-row">
          <span class="muted">
            Страница {{ materialPagination.page }} из {{ materialPagination.pages }}. Всего: {{ materialPagination.total }}
          </span>
          <div class="table-actions">
            <button
              class="button button-secondary"
              type="button"
              :disabled="materialPage <= 1"
              @click="materialPage -= 1"
            >
              Назад
            </button>
            <button
              class="button button-secondary"
              type="button"
              :disabled="materialPage >= materialPagination.pages"
              @click="materialPage += 1"
            >
              Вперёд
            </button>
          </div>
        </div>
      </div>
    </Modal>
  </Modal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import type { Pagination } from '../../types/api'
import type {
  ComponentType,
  ImportMaterialCreateResult,
  ImportedSpecificationRow,
  MaterialRecord,
  MissingImportedMaterial,
  UnitRecord,
  WorkDetail,
  WorkRecord,
  WorkSpecificationRecord,
} from '../../types/models'
import Modal from '../common/Modal.vue'
import FormField from '../common/FormField.vue'
import { clearWorkCatalogCache, loadWorkCatalog } from '../../api/workCatalog'
import { useSpecificationReview } from '../../composables/useSpecificationReview'
import {
  buildWorkSpecificationExport,
  cloneSpecificationRow,
  createImportMaterials,
  createEmptySpecificationRow,
  createWork,
  getWork,
  listMaterials,
  listUnits,
  previewCopySpecifications,
  previewSpecificationImport,
  toWorkPayload,
  updateMaterial,
  updateWork,
} from '../../api/works'

type WorkField = 'name' | 'code' | 'unit'
type WorkNumericField = 'price' | 'labor_rate'
type SpecNumericField = 'consumption_rate' | 'unit_price'
type ImportTextField = 'component_name' | 'unit_name' | 'consumption_rate' | 'unit_price'

interface EditableWork {
  id: number | null
  name: string
  code: string
  unit: string
  price: number
  labor_rate: number
  specification_review_status: 'ok' | 'incorrect' | 'corrected'
  specification_review_note: string
  parent_id: number | null
  marked_for_deletion: boolean
  is_group: boolean
}

interface EditableSpecification extends Omit<WorkSpecificationRecord, 'work_id'> {
  localId: string
}

interface ImportDraftRow {
  id: string
  source_row: number
  component_type: ComponentType | ''
  component_name: string
  material_code?: string | null
  material_id?: number | null
  material_status?: 'existing' | 'new' | null
  matched_material_name?: string | null
  matched_material_code?: string | null
  unit_name: string
  unit_id?: number | null
  unit_status?: 'existing' | 'new' | null
  warnings?: string[]
  consumption_rate: string
  unit_price: string
}

interface GroupOption {
  id: number
  label: string
}

const STORAGE_KEY = 'work-form:specification-collapsed'
const MAIN_SECTION_STORAGE_KEY = 'work-form:main-section-collapsed'
const componentTypeOptions: Array<{ value: ComponentType; label: string }> = [
  { value: 'Material', label: 'Материал' },
  { value: 'Labor', label: 'Труд' },
  { value: 'Equipment', label: 'Оборудование' },
  { value: 'Other', label: 'Прочее' },
]
const reviewStatusOptions = [
  { value: 'ok' as const, label: 'ОК' },
  { value: 'incorrect' as const, label: 'Некорректно' },
  { value: 'corrected' as const, label: 'Исправлено' },
]
const { specificationReviewEnabled } = useSpecificationReview()

const props = defineProps<{
  open: boolean
  workId: number | null
}>()

const emit = defineEmits<{
  close: []
  saved: [work: WorkDetail]
}>()

const work = reactive<EditableWork>(createEmptyWork())
const specifications = ref<EditableSpecification[]>([])
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const errorMessage = ref('')
const saveMessage = ref('')
const units = ref<UnitRecord[]>([])
const workCatalog = ref<WorkRecord[]>([])
const fieldErrors = reactive<Record<string, string>>({})
const rowTouched = reactive<Record<string, boolean>>({})
const fieldFeedback = reactive<Record<string, string>>({})
const showAllRowErrors = ref(false)

const collapsed = ref(readCollapsedState())
const mainSectionCollapsed = ref(readMainSectionState())
const searchInput = ref('')
const debouncedSearch = ref('')
let searchTimer = 0
let materialSearchTimer = 0
let localCounter = 0

const typeFilter = ref<'All' | ComponentType>('All')
const importInputRef = ref<HTMLInputElement | null>(null)

const copyModalOpen = ref(false)
const copySearch = ref('')
const copyError = ref('')
const selectedCopySourceId = ref<number | null>(null)
const copyPreviewLoading = ref(false)
const copyPreviewRows = ref<WorkSpecificationRecord[]>([])

const importModalOpen = ref(false)
const importFileName = ref('')
const importError = ref('')
const importMessage = ref('')
const importRows = ref<ImportDraftRow[]>([])
const creatingImportMaterials = ref(false)
const importApplyMode = ref<'append' | 'replace'>('append')

const materialModalOpen = ref(false)
const materialTargetLocalId = ref<string | null>(null)
const materialSearch = ref('')
const materialPage = ref(1)
const materials = ref<MaterialRecord[]>([])
const materialLoading = ref(false)
const materialError = ref('')
const materialPagination = reactive<Pagination>({
  page: 1,
  page_size: 20,
  total: 0,
  pages: 1,
})
const editingMaterialId = ref<number | null>(null)
const editingMaterial = reactive({ name: '', code: '', unit_name: '', price: 0 })
const savingMaterial = ref(false)
const materialCatalog = ref<MaterialRecord[]>([])

const hasHiddenGroupValues = computed(() => work.price !== 0 || work.labor_rate !== 0)

const componentNameSuggestions = computed(() => {
  const values = new Set(
    specifications.value
      .map((row) => row.component_name.trim())
      .filter((value) => value.length > 0),
  )
  return [...values].sort((left, right) => left.localeCompare(right, 'ru', { sensitivity: 'base' }))
})

const visibleSpecifications = computed(() => {
  const query = debouncedSearch.value.trim().toLowerCase()

  return specifications.value.filter((row) => {
    const matchesType = typeFilter.value === 'All' || row.component_type === typeFilter.value
    const matchesSearch = query.length === 0 || row.component_name.toLowerCase().includes(query)
    return matchesType && matchesSearch
  })
})

const overallTotal = computed(() =>
  roundMoney(specifications.value.reduce((sum, row) => sum + Number(row.total_cost || 0), 0)),
)

const visibleSubtotals = computed(() =>
  componentTypeOptions.map((option) => ({
    type: option.value,
    label: option.label,
    total: roundMoney(
      visibleSpecifications.value
        .filter((row) => row.component_type === option.value)
        .reduce((sum, row) => sum + Number(row.total_cost || 0), 0),
    ),
  })),
)

const visibleTotal = computed(() =>
  roundMoney(visibleSubtotals.value.reduce((sum, item) => sum + item.total, 0)),
)

const filtersActive = computed(() => debouncedSearch.value.trim().length > 0 || typeFilter.value !== 'All')

const summaryCaption = computed(() =>
  filtersActive.value ? 'Итоги по отфильтрованным строкам' : 'Итоги по всей спецификации',
)

const laborWarning = computed(() => {
  if (work.is_group) {
    return ''
  }
  const hasLabor = specifications.value.some((row) => row.component_type === 'Labor')
  return hasLabor ? '' : 'В спецификации нет строк типа «Труд». Сохранение доступно, но проверьте состав работы.'
})

const groupOptions = computed(() => buildGroupOptions(workCatalog.value, work.id))

const copySourceOptions = computed(() => {
  const query = copySearch.value.trim().toLowerCase()
  return workCatalog.value.filter((item) => {
    if (item.is_group || item.marked_for_deletion || item.id === work.id) {
      return false
    }
    if (!query) {
      return true
    }
    return item.name.toLowerCase().includes(query) || (item.code ?? '').toLowerCase().includes(query)
  })
})

const validImportRows = computed(() =>
  importRows.value
    .filter((row) => importRowErrors(row).length === 0)
    .map((row) => ({
      component_type: row.component_type as ComponentType,
      component_name: row.component_name.trim(),
      material_id: row.material_id ?? null,
      unit_name: row.unit_name.trim(),
      unit_id: row.unit_id ?? resolveUnitId(row.unit_name),
      consumption_rate: parseDecimal(row.consumption_rate),
      unit_price: parseDecimal(row.unit_price),
    })),
)

const missingImportMaterials = computed<MissingImportedMaterial[]>(() => {
  const grouped = new Map<string, MissingImportedMaterial>()

  for (const row of importRows.value) {
    if (!usesMaterialCatalog(row.component_type) || row.material_id) {
      continue
    }
    if (!row.component_name.trim() || !row.unit_name.trim()) {
      continue
    }

    const price = parseDecimal(row.unit_price)
    if (!Number.isFinite(price) || price < 0) {
      continue
    }

    const key = row.material_code?.trim()
      ? `code:${row.material_code.trim().toLowerCase()}`
      : `name:${row.component_name.trim().toLowerCase()}`
    const existing = grouped.get(key)

    if (existing) {
      if (!existing.source_row_numbers.includes(row.source_row)) {
        existing.source_row_numbers.push(row.source_row)
      }
      if (!existing.unit_name && row.unit_name.trim()) {
        existing.unit_name = row.unit_name.trim()
      }
      if (existing.unit_id == null && row.unit_id != null) {
        existing.unit_id = row.unit_id
      }
      if (!existing.unit_status && row.unit_status) {
        existing.unit_status = row.unit_status
      }
      if (existing.unit_price === 0 && price > 0) {
        existing.unit_price = price
      }
      continue
    }

    grouped.set(key, {
      material_name: row.component_name.trim(),
      material_code: row.material_code?.trim() || null,
      unit_name: row.unit_name.trim(),
      unit_id: row.unit_id ?? resolveUnitId(row.unit_name),
      unit_status: row.unit_status ?? null,
      unit_price: price,
      source_row_numbers: [row.source_row],
    })
  }

  return Array.from(grouped.values())
})

// NEW: Unit statistics for import preview
const importUnitStats = computed(() => {
  const existing = importRows.value.filter(row => row.unit_status === 'existing').length
  const newUnits = importRows.value.filter(row => row.unit_status === 'new').length
  const uniqueNewUnits = new Set(
    importRows.value
      .filter(row => row.unit_status === 'new')
      .map(row => row.unit_name)
  )
  
  return {
    existingCount: existing,
    newCount: newUnits,
    uniqueNewUnits: Array.from(uniqueNewUnits),
  }
})

const hasImportWarnings = computed(() => 
  importRows.value.some(row => row.warnings && row.warnings.length > 0)
)

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      return
    }
    await initializeForm()
  },
)

watch(searchInput, (value) => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    debouncedSearch.value = value
  }, 180)
})

watch(materialPage, () => {
  if (!materialModalOpen.value) {
    return
  }
  loadMaterials()
})

watch(materialSearch, () => {
  if (!materialModalOpen.value) {
    return
  }
  window.clearTimeout(materialSearchTimer)
  materialSearchTimer = window.setTimeout(() => {
    materialPage.value = 1
    loadMaterials()
  }, 250)
})

onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
  window.clearTimeout(materialSearchTimer)
})

function createEmptyWork(): EditableWork {
  return {
    id: null,
    name: '',
    code: '',
    unit: '',
    price: 0,
    labor_rate: 0,
    specification_review_status: 'ok',
    specification_review_note: '',
    parent_id: null,
    marked_for_deletion: false,
    is_group: false,
  }
}

function nextLocalId(prefix = 'spec') {
  localCounter += 1
  return `${prefix}-${Date.now()}-${localCounter}`
}

function roundMoney(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

function parseDecimal(value: string) {
  const normalized = value.trim().replace(',', '.')
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : Number.NaN
}

function formatMoney(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value ?? 0)
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 4,
  }).format(value ?? 0)
}

function formatNumericInput(value: number) {
  return Number.isFinite(value) ? String(value) : '0'
}

function componentTypeLabel(value: ComponentType) {
  return componentTypeOptions.find((option) => option.value === value)?.label ?? value
}

function usesMaterialCatalog(value: ComponentType | '' | null | undefined) {
  return value === 'Material' || value === 'Labor'
}

function readCollapsedState() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function readMainSectionState() {
  try {
    return localStorage.getItem(MAIN_SECTION_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value
  try {
    localStorage.setItem(STORAGE_KEY, String(collapsed.value))
  } catch {
    // ignore storage failures
  }
}

function toggleMainSection() {
  mainSectionCollapsed.value = !mainSectionCollapsed.value
  try {
    localStorage.setItem(MAIN_SECTION_STORAGE_KEY, String(mainSectionCollapsed.value))
  } catch {
    // ignore storage failures
  }
}

function clearMessages() {
  errorMessage.value = ''
  saveMessage.value = ''
}

function resetFieldErrors() {
  Object.keys(fieldErrors).forEach((key) => delete fieldErrors[key])
}

function resetRowState() {
  Object.keys(rowTouched).forEach((key) => delete rowTouched[key])
  Object.keys(fieldFeedback).forEach((key) => delete fieldFeedback[key])
  showAllRowErrors.value = false
}

function markDirty() {
  dirty.value = true
  saveMessage.value = ''
}

function resetWorkState() {
  Object.assign(work, createEmptyWork())
  specifications.value = []
  dirty.value = false
  searchInput.value = ''
  debouncedSearch.value = ''
  typeFilter.value = 'All'
  clearMessages()
  copySearch.value = ''
  copyError.value = ''
  selectedCopySourceId.value = null
  copyPreviewLoading.value = false
  copyPreviewRows.value = []
  importFileName.value = ''
  importError.value = ''
  importMessage.value = ''
  importRows.value = []
  creatingImportMaterials.value = false
  importApplyMode.value = 'append'
  materialSearch.value = ''
  materialPage.value = 1
  materials.value = []
  materialLoading.value = false
  materialError.value = ''
  resetFieldErrors()
  resetRowState()
}

function applyWorkDetail(detail: WorkDetail) {
  resetFieldErrors()
  resetRowState()
  Object.assign(work, {
    id: detail.id,
    name: detail.name ?? '',
    code: detail.code ?? '',
    unit: detail.unit ?? '',
    price: Number(detail.price || 0),
    labor_rate: Number(detail.labor_rate || 0),
    specification_review_status: detail.specification_review_status ?? 'ok',
    specification_review_note: detail.specification_review_note ?? '',
    parent_id: detail.parent_id ?? null,
    marked_for_deletion: Boolean(detail.marked_for_deletion),
    is_group: Boolean(detail.is_group),
  })

  specifications.value = detail.specifications.map((row) => ({
    ...row,
    localId: nextLocalId(),
    total_cost: roundMoney(Number(row.consumption_rate || 0) * Number(row.unit_price || 0)),
  }))
}

async function initializeForm() {
  loading.value = true
  resetWorkState()

  const [catalogResult, unitResult, materialResult] = await Promise.allSettled([
      loadWorkCatalog(true),
      listUnits(),
      listMaterials({ page_size: 100 }),
    ])

    if (catalogResult.status === 'fulfilled') {
      workCatalog.value = catalogResult.value
    } else {
      console.warn('Failed to load work catalog:', catalogResult.reason)
    }

    if (unitResult.status === 'fulfilled') {
      units.value = unitResult.value.data
    } else {
      console.warn('Failed to load units:', unitResult.reason)
    }

    if (materialResult.status === 'fulfilled') {
      materialCatalog.value = materialResult.value.data
    } else {
      console.warn('Failed to load materials:', materialResult.reason)
    }

    // Load work detail independently — critical path, report errors to the user
    if (props.workId) {
      try {
        const response = await getWork(props.workId)
        applyWorkDetail(response.data)
      } catch (err) {
        errorMessage.value = err instanceof Error ? err.message : 'Не удалось загрузить карточку работы'
      }
    }

    loading.value = false
}

function buildGroupOptions(items: WorkRecord[], currentId: number | null) {
  const groups = items.filter((item) => item.is_group && !item.marked_for_deletion && item.id !== currentId)
  const children = new Map<number | null, WorkRecord[]>()
  groups.forEach((item) => {
    const parentId = item.parent_id ?? null
    const bucket = children.get(parentId) ?? []
    bucket.push(item)
    children.set(parentId, bucket)
  })

  const result: GroupOption[] = []
  const visited = new Set<number>()

  function walk(parentId: number | null, level: number) {
    const nodes = children.get(parentId) ?? []
    nodes.forEach((node) => {
      if (visited.has(node.id)) {
        return
      }
      visited.add(node.id)
      result.push({ id: node.id, label: `${'— '.repeat(level)}${node.name}` })
      walk(node.id, level + 1)
    })
  }

  walk(null, 0)
  return result
}

function handleWorkTextInput(field: WorkField, event: Event) {
  const value = (event.target as HTMLInputElement).value
  work[field] = value
  markDirty()
  if (field === 'name') {
    delete fieldErrors.name
  }
}

function handleWorkNumberChange(field: WorkNumericField, event: Event) {
  const input = event.target as HTMLInputElement
  const parsed = parseDecimal(input.value)

  if (!Number.isFinite(parsed) || parsed < 0) {
    fieldErrors[field] =
      field === 'price' ? 'Цена должна быть не меньше нуля' : 'Норма труда должна быть не меньше нуля'
    input.value = formatNumericInput(work[field])
    return
  }

  work[field] = parsed
  delete fieldErrors[field]
  markDirty()
}

function handleReviewStatusChange(event: Event) {
  work.specification_review_status = (event.target as HTMLSelectElement).value as EditableWork['specification_review_status']
  markDirty()
}

function handleReviewNoteInput(event: Event) {
  work.specification_review_note = (event.target as HTMLInputElement).value
  markDirty()
}

function handleParentChange(event: Event) {
  const rawValue = (event.target as HTMLSelectElement).value
  work.parent_id = rawValue ? Number(rawValue) : null
  markDirty()
}

function handleGroupToggle(event: Event) {
  work.is_group = (event.target as HTMLInputElement).checked
  delete fieldErrors.group
  markDirty()
}

function clearGroupValues() {
  work.price = 0
  work.labor_rate = 0
  delete fieldErrors.group
  delete fieldErrors.price
  delete fieldErrors.labor_rate
  markDirty()
}

function recalculateRow(row: EditableSpecification) {
  row.total_cost = roundMoney(Number(row.consumption_rate || 0) * Number(row.unit_price || 0))
}

function addRow() {
  const row = {
    ...createEmptySpecificationRow(),
    localId: nextLocalId(),
  } as EditableSpecification

  recalculateRow(row)
  specifications.value = [...specifications.value, row]
  rowTouched[row.localId] = true
  markDirty()
}

function updateRowType(row: EditableSpecification, event: Event) {
  row.component_type = (event.target as HTMLSelectElement).value as ComponentType
  if (!usesMaterialCatalog(row.component_type)) {
    row.material_id = null
  }
  rowTouched[row.localId] = true
  markDirty()
}

function updateRowText(row: EditableSpecification, field: 'component_name', event: Event) {
  row[field] = (event.target as HTMLInputElement).value
  if (field === 'component_name' && usesMaterialCatalog(row.component_type)) {
    row.material_id = null
    const matched = materialCatalog.value.find(
      (m) => m.name.trim().toLowerCase() === row.component_name.trim().toLowerCase(),
    )
    if (matched) {
      row.material_id = matched.id ?? null
      row.unit_id = matched.unit_id ?? null
      row.unit_name = matched.unit_name ?? row.unit_name
      row.unit_price = Number(matched.price || 0)
      recalculateRow(row)
    }
  }
  rowTouched[row.localId] = true
  delete fieldFeedback[`${row.localId}:${field}`]
  markDirty()
}

function resolveUnitId(unitName: string) {
  const normalized = unitName.trim().toLowerCase()
  if (!normalized) {
    return null
  }

  const matchedUnit = units.value.find((unit) => {
    const name = unit.name.trim().toLowerCase()
    const shortName = (unit.short_name ?? '').trim().toLowerCase()
    return normalized === name || normalized === shortName
  })

  return matchedUnit?.id ?? null
}

function updateRowUnit(row: EditableSpecification, event: Event) {
  const value = (event.target as HTMLInputElement).value
  row.unit_name = value
  row.unit_id = resolveUnitId(value)
  rowTouched[row.localId] = true
  delete fieldFeedback[`${row.localId}:unit_name`]
  markDirty()
}

function handleRowNumberChange(row: EditableSpecification, field: SpecNumericField, event: Event) {
  const input = event.target as HTMLInputElement
  const parsed = parseDecimal(input.value)
  const errorKey = `${row.localId}:${field}`
  const minValue = field === 'consumption_rate' ? 0 : -1

  if (!Number.isFinite(parsed) || parsed <= minValue) {
    fieldFeedback[errorKey] =
      field === 'consumption_rate'
        ? 'Норма расхода должна быть больше нуля'
        : 'Цена должна быть не меньше нуля'
    input.value = formatNumericInput(row[field])
    rowTouched[row.localId] = true
    return
  }

  row[field] = parsed
  delete fieldFeedback[errorKey]
  rowTouched[row.localId] = true
  recalculateRow(row)
  markDirty()
}

function rowValidationErrors(row: EditableSpecification) {
  const errors: string[] = []
  if (!row.component_type) {
    errors.push('Не указан тип компонента')
  }
  if (!row.component_name.trim()) {
    errors.push('Не указано наименование')
  }
  if (!(row.unit_name ?? '').trim()) {
    errors.push('Не указана единица измерения')
  }
  if (!Number.isFinite(row.consumption_rate) || row.consumption_rate <= 0) {
    errors.push('Норма расхода должна быть больше нуля')
  }
  if (!Number.isFinite(row.unit_price) || row.unit_price < 0) {
    errors.push('Цена должна быть не меньше нуля')
  }
  return errors
}

function rowMessages(row: EditableSpecification) {
  const feedback = Object.entries(fieldFeedback)
    .filter(([key]) => key.startsWith(`${row.localId}:`))
    .map(([, value]) => value)
  return [...new Set([...rowValidationErrors(row), ...feedback])]
}

function shouldShowRowErrors(row: EditableSpecification) {
  return (showAllRowErrors.value || rowTouched[row.localId]) && rowMessages(row).length > 0
}

function removeRow(localId: string) {
  if (!window.confirm('Удалить строку спецификации?')) {
    return
  }

  specifications.value = specifications.value.filter((row) => row.localId !== localId)
  delete rowTouched[localId]
  Object.keys(fieldFeedback)
    .filter((key) => key.startsWith(`${localId}:`))
    .forEach((key) => delete fieldFeedback[key])
  markDirty()
}

function validateForm() {
  clearMessages()
  resetFieldErrors()
  showAllRowErrors.value = true

  let isValid = true

  if (!work.name.trim()) {
    fieldErrors.name = 'Укажите наименование работы'
    isValid = false
  }

  if (work.is_group && hasHiddenGroupValues.value) {
    fieldErrors.group = 'Групповая работа не может иметь цену или норму труда'
    isValid = false
  }

  if (!work.is_group && specifications.value.length === 0) {
    errorMessage.value = 'Для негрупповой работы нужно заполнить хотя бы одну строку спецификации'
    isValid = false
  }

  if (specifications.value.some((row) => rowMessages(row).length > 0)) {
    errorMessage.value = 'Исправьте ошибки в строках спецификации перед сохранением'
    isValid = false
  }

  if (!isValid) {
    mainSectionCollapsed.value = false
  }

  return isValid
}

async function saveWork() {
  if (!validateForm()) {
    return
  }

  saving.value = true
  clearMessages()

  try {
    const payload = toWorkPayload(
      {
        id: work.id ?? 0,
        name: work.name.trim(),
        code: work.code.trim() || null,
        unit: work.unit.trim() || null,
        price: work.price,
        labor_rate: work.labor_rate,
        parent_id: work.parent_id,
        marked_for_deletion: work.marked_for_deletion,
        is_group: work.is_group,
      },
      specifications.value,
    )

    const response = work.id ? await updateWork(work.id, payload) : await createWork(payload)
    applyWorkDetail(response.data)
    dirty.value = false
    saveMessage.value = 'Карточка сохранена'
    clearWorkCatalogCache()
    workCatalog.value = await loadWorkCatalog(true)
    emit('saved', response.data)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Не удалось сохранить карточку работы'
  } finally {
    saving.value = false
  }
}

async function cancelEdits() {
  if (!dirty.value) {
    return
  }

  if (!window.confirm('Отменить несохранённые изменения?')) {
    return
  }

  if (!props.workId) {
    resetWorkState()
    return
  }

  loading.value = true
  clearMessages()

  try {
    const response = await getWork(props.workId)
    applyWorkDetail(response.data)
    dirty.value = false
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Не удалось восстановить карточку работы'
  } finally {
    loading.value = false
  }
}

function requestClose() {
  if (dirty.value && !window.confirm('Есть несохранённые изменения. Закрыть карточку?')) {
    return
  }
  emit('close')
}

function openCopyModal() {
  copyModalOpen.value = true
  copyError.value = ''
  copySearch.value = ''
  selectedCopySourceId.value = null
  copyPreviewRows.value = []
}

function closeCopyModal() {
  copyModalOpen.value = false
  copyError.value = ''
  selectedCopySourceId.value = null
  copyPreviewLoading.value = false
  copyPreviewRows.value = []
}

async function selectCopySource(sourceId: number) {
  selectedCopySourceId.value = sourceId
  copyPreviewLoading.value = true
  copyError.value = ''

  try {
    const response = await previewCopySpecifications(work.id ?? 0, sourceId)
    copyPreviewRows.value = response.data.rows
  } catch (err) {
    copyError.value = err instanceof Error ? err.message : 'Не удалось получить состав работы-источника'
    copyPreviewRows.value = []
  } finally {
    copyPreviewLoading.value = false
  }
}

function applyCopyPreview() {
  const rowsToAdd: EditableSpecification[] = copyPreviewRows.value.map((row) => ({
    ...cloneSpecificationRow(row),
    localId: nextLocalId(),
  }))

  rowsToAdd.forEach((row) => recalculateRow(row))
  specifications.value = [...specifications.value, ...rowsToAdd]
  rowsToAdd.forEach((row) => {
    rowTouched[row.localId] = true
  })
  markDirty()
  closeCopyModal()
}

function triggerImport() {
  importInputRef.value?.click()
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) {
    return
  }

  importError.value = ''
  importMessage.value = ''
  creatingImportMaterials.value = false

  try {
    const response = await previewSpecificationImport(work.id ?? 0, file)
    importFileName.value = file.name
    importRows.value = response.data.rows.map((row) => mapImportRow(row))
    importApplyMode.value = specifications.value.length > 0 ? 'append' : 'replace'
    importModalOpen.value = true
  } catch (err) {
    importError.value = err instanceof Error ? err.message : 'Не удалось импортировать файл'
    importModalOpen.value = true
  } finally {
    ;(event.target as HTMLInputElement).value = ''
  }
}

function mapImportRow(row: ImportedSpecificationRow): ImportDraftRow {
  return {
    id: nextLocalId('import'),
    source_row: row.source_row,
    component_type: (row.component_type as ComponentType | null) ?? '',
    component_name: row.component_name ?? '',
    material_code: row.material_code ?? null,
    material_id: row.material_id ?? null,
    material_status: row.material_status ?? null,
    matched_material_name: row.matched_material_name ?? null,
    matched_material_code: row.matched_material_code ?? null,
    unit_name: row.unit_name ?? '',
    unit_id: row.unit_id ?? null,
    unit_status: row.unit_status ?? null,
    warnings: row.warnings ?? [],
    consumption_rate:
      row.consumption_rate !== null && row.consumption_rate !== undefined ? String(row.consumption_rate) : '',
    unit_price: row.unit_price !== null && row.unit_price !== undefined ? String(row.unit_price) : '',
  }
}

function updateImportType(row: ImportDraftRow, event: Event) {
  row.component_type = (event.target as HTMLSelectElement).value as ComponentType | ''
  if (!usesMaterialCatalog(row.component_type)) {
    row.material_id = null
    row.material_status = null
    row.matched_material_name = null
    row.matched_material_code = null
    row.material_code = null
  }
}

function updateImportText(row: ImportDraftRow, field: ImportTextField, event: Event) {
  const value = (event.target as HTMLInputElement).value
  row[field] = value

  if (field === 'unit_name') {
    row.unit_id = resolveUnitId(value)
    row.unit_status = row.unit_id ? 'existing' : 'new'
  }

  if (field === 'component_name' && usesMaterialCatalog(row.component_type)) {
    row.material_id = null
    row.material_status = 'new'
    row.matched_material_name = null
    row.matched_material_code = null
  }
}

function importRowTotal(row: ImportDraftRow) {
  const rate = parseDecimal(row.consumption_rate)
  const price = parseDecimal(row.unit_price)
  if (!Number.isFinite(rate) || !Number.isFinite(price)) {
    return 0
  }
  return roundMoney(rate * price)
}

function importRowErrors(row: ImportDraftRow) {
  const errors: string[] = []
  if (!row.component_type) {
    errors.push('Не указан тип компонента')
  }
  if (!row.component_name.trim()) {
    errors.push('Не указано наименование')
  }
  if (!row.unit_name.trim()) {
    errors.push('Не указана единица измерения')
  }

  const rate = parseDecimal(row.consumption_rate)
  if (!Number.isFinite(rate) || rate <= 0) {
    errors.push('Норма расхода должна быть больше нуля')
  }

  const price = parseDecimal(row.unit_price)
  if (!Number.isFinite(price) || price < 0) {
    errors.push('Цена должна быть не меньше нуля')
  }

  if (usesMaterialCatalog(row.component_type) && !row.material_id) {
    errors.push('Элемент не найден в справочнике материалов')
  }

  return errors
}

function applyCreatedImportMaterials(materials: ImportMaterialCreateResult[]) {
  const rowsBySource = new Map<number, ImportMaterialCreateResult>()
  for (const material of materials) {
    for (const sourceRow of material.source_row_numbers) {
      rowsBySource.set(sourceRow, material)
    }
  }

  for (const row of importRows.value) {
    const resolved = rowsBySource.get(row.source_row)
    if (!resolved || !usesMaterialCatalog(row.component_type)) {
      continue
    }
    row.material_id = resolved.material_id
    row.material_status = 'existing'
    row.matched_material_name = resolved.material_name
    row.matched_material_code = resolved.material_code ?? null
    row.material_code = row.material_code ?? resolved.material_code ?? null
    row.unit_id = resolved.unit_id ?? row.unit_id ?? null
    row.unit_name = row.unit_name.trim() || resolved.unit_name || ''
    row.unit_status = resolved.unit_id ? 'existing' : row.unit_status ?? null
  }
}

async function createMissingImportMaterials() {
  if (missingImportMaterials.value.length === 0) {
    return
  }

  creatingImportMaterials.value = true
  importError.value = ''
  importMessage.value = ''

  try {
    const response = await createImportMaterials(work.id ?? 0, missingImportMaterials.value)
    applyCreatedImportMaterials(response.data.materials)
    const unitsResponse = await listUnits()
    units.value = unitsResponse.data
    importMessage.value =
      response.data.created_count > 0
        ? `Создано материалов: ${response.data.created_count}. Переиспользовано: ${response.data.reused_count}.`
        : `Все материалы уже существовали. Переиспользовано: ${response.data.reused_count}.`
  } catch (err) {
    importError.value = err instanceof Error ? err.message : 'Не удалось создать материалы для импорта'
  } finally {
    creatingImportMaterials.value = false
  }
}

function applyImportRows(mode: 'append' | 'replace' = importApplyMode.value) {
  const rowsToImport: EditableSpecification[] = validImportRows.value.map((row) => ({
    localId: nextLocalId(),
    component_type: row.component_type,
    component_name: row.component_name,
    unit_id: row.unit_id ?? resolveUnitId(row.unit_name),
    unit_name: row.unit_name,
    consumption_rate: row.consumption_rate,
    unit_price: row.unit_price,
    total_cost: roundMoney(row.consumption_rate * row.unit_price),
    material_id: row.material_id ?? null,
  }))

  if (mode === 'replace' && specifications.value.length > 0) {
    specifications.value = rowsToImport
  } else {
    specifications.value = [...specifications.value, ...rowsToImport]
  }
  rowsToImport.forEach((row) => {
    rowTouched[row.localId] = true
  })
  markDirty()
  closeImportModal()
}

function closeImportModal() {
  importModalOpen.value = false
  importError.value = ''
  importMessage.value = ''
  creatingImportMaterials.value = false
}

function openMaterialModal(row: EditableSpecification, initialSearch = '') {
  materialTargetLocalId.value = row.localId
  materialSearch.value = initialSearch.trim()
  materialPage.value = 1
  materialModalOpen.value = true
  loadMaterials()
}

function closeMaterialModal() {
  materialModalOpen.value = false
  materialTargetLocalId.value = null
  materialError.value = ''
  materialLoading.value = false
  materials.value = []
  editingMaterialId.value = null
}

function startEditMaterial(material: MaterialRecord) {
  editingMaterialId.value = material.id
  editingMaterial.name = material.name
  editingMaterial.code = material.code ?? ''
  editingMaterial.unit_name = material.unit_name ?? ''
  editingMaterial.price = material.price
}

function cancelEditMaterial() {
  editingMaterialId.value = null
}

async function saveEditedMaterial() {
  if (!editingMaterialId.value) return
  savingMaterial.value = true
  try {
    const matchedUnit = units.value.find((u) => u.name === editingMaterial.unit_name)
    await updateMaterial(editingMaterialId.value, {
      name: editingMaterial.name,
      code: editingMaterial.code,
      price: editingMaterial.price,
      unit_id: matchedUnit?.id ?? undefined,
    })
    editingMaterialId.value = null
    await loadMaterials()
  } catch (err) {
    materialError.value = err instanceof Error ? err.message : 'Не удалось сохранить материал'
  } finally {
    savingMaterial.value = false
  }
}

async function loadMaterials() {
  materialLoading.value = true
  materialError.value = ''

  try {
    const response = await listMaterials({
      page: materialPage.value,
      page_size: 20,
      search: materialSearch.value,
    })
    materials.value = response.data
    materialPagination.page = response.pagination?.page ?? 1
    materialPagination.page_size = response.pagination?.page_size ?? 20
    materialPagination.total = response.pagination?.total ?? 0
    materialPagination.pages = response.pagination?.pages ?? 1
  } catch (err) {
    materialError.value = err instanceof Error ? err.message : 'Не удалось загрузить материалы'
  } finally {
    materialLoading.value = false
  }
}

function applyMaterial(material: MaterialRecord) {
  const row = specifications.value.find((item) => item.localId === materialTargetLocalId.value)
  if (!row) {
    return
  }

  row.component_name = material.name
  row.material_id = material.id
  row.unit_id = material.unit_id ?? null
  row.unit_name = material.unit_name ?? ''
  row.unit_price = Number(material.price || 0)
  recalculateRow(row)
  rowTouched[row.localId] = true
  markDirty()
  closeMaterialModal()
}

function exportCurrentSpecification() {
  const blob = buildWorkSpecificationExport(
    {
      name: work.name.trim() || 'Новая работа',
      code: work.code.trim() || null,
      unit: work.unit.trim() || null,
    },
    specifications.value,
  )

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const safeName = (work.name.trim() || 'work-specification').replace(/[\\/:*?"<>|]+/g, '_')
  link.href = url
  link.download = `${safeName}.xls`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.work-form {
  display: grid;
  grid-template-rows: auto auto minmax(16rem, 1fr);
  width: min(1040px, 100%);
  max-width: 100%;
  min-height: 0;
  height: 100%;
  margin: 0 auto;
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 10px 15px -12px rgba(15, 23, 42, 0.24);
}

.work-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.55rem 0.85rem;
  border-bottom: 1px solid rgba(226, 232, 240, 0.95);
  background: #f8fafc;
}

.work-topbar-main {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  min-width: 0;
}

.work-card-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
}

.work-topbar :deep(.status-pill) {
  padding: 0.26rem 0.58rem;
  border-radius: 999px;
  font-size: 0.72rem;
}

.work-topbar-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.work-icon-button {
  width: 2.15rem;
  min-width: 2.15rem;
  height: 2.15rem;
  padding: 0;
  border-radius: 999px;
  font-size: 1rem;
  line-height: 1;
}

.work-icon-button-primary {
  font-weight: 700;
}

.panel-stack { display: grid; gap: 0.6rem; }
.section-title {
  margin: 0;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-soft);
}
.section-subtitle {
  display: none;
}
.message-banner {
  border-radius: 8px;
  padding: 0.55rem 0.7rem;
  font-size: 0.84rem;
}
.message-error { background: rgba(160, 50, 50, 0.12); color: var(--danger); }
.message-success { background: rgba(45, 122, 68, 0.12); color: var(--success); }
.message-warning { background: rgba(178, 126, 45, 0.12); color: #7c5617; }
.inline-button { display: inline-flex; margin-left: 0.65rem; padding-block: 0.32rem; }

.work-main-panel {
  min-height: 0;
  overflow: hidden;
  border: none;
  border-bottom: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.work-section-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border: none;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  background: #ffffff;
  padding: 0.55rem 0.9rem;
  text-align: left;
}

.work-section-toggle-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.work-section-toggle-icon {
  color: var(--text-soft);
  font-size: 0.72rem;
}

.work-section-toggle-state {
  color: var(--text-soft);
  font-size: 0.74rem;
}

.work-main-panel-body {
  gap: 0.6rem;
  min-height: 0;
  overflow: auto;
  padding: 0.7rem 0.9rem 0.85rem;
}

.work-basic-grid {
  display: grid;
  gap: 0.6rem 0.7rem;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  align-items: start;
}

.work-field-span-1 { grid-column: span 1; }
.work-field-span-2 { grid-column: span 2; }
.work-field-span-3 { grid-column: span 3; }
.work-field-span-4 { grid-column: span 4; }

.work-basic-grid :deep(.field),
.work-review-grid :deep(.field) {
  position: relative;
  gap: 0.18rem;
}

.work-basic-grid :deep(.field-label),
.work-review-grid :deep(.field-label) {
  position: absolute;
  top: 0.36rem;
  left: 0.62rem;
  z-index: 1;
  pointer-events: none;
  color: var(--text-soft);
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.work-basic-grid :deep(.field-error),
.work-review-grid :deep(.field-error) {
  font-size: 0.74rem;
}

.work-compact-control {
  min-height: 2.8rem;
  border-radius: 6px;
  padding: 1.15rem 0.6rem 0.35rem;
}

.work-flat-control {
  border: 1px solid transparent;
  background: transparent;
  box-shadow: none;
  transition: border-color 140ms ease, background-color 140ms ease, box-shadow 140ms ease;
}

.work-flat-control:hover {
  background: #f8fafc;
  border-color: rgba(226, 232, 240, 0.95);
}

.work-flat-control:focus,
.work-flat-control:focus-visible {
  background: #ffffff;
  border-color: #3b82f6;
  outline: none;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.12);
}

.work-number-control {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.checkbox-row {
  display: flex;
  align-items: flex-end;
  gap: 0.65rem;
  min-height: 2.8rem;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  padding: 1.15rem 0.6rem 0.4rem;
  transition: border-color 140ms ease, background-color 140ms ease;
}

.checkbox-row:hover {
  background: #f8fafc;
  border-color: rgba(226, 232, 240, 0.95);
}

.work-review-card {
  display: grid;
  gap: 0.45rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 8px;
  background: #f8fafc;
  padding: 0.65rem 0.75rem;
}

.work-review-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
  font-size: 0.82rem;
}

.work-review-grid {
  display: grid;
  gap: 0.6rem;
  grid-template-columns: minmax(0, 13rem) minmax(0, 1fr);
}

.specification-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.specification-header {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.85rem;
  border: none;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  background: #ffffff;
  color: inherit;
  text-align: left;
  padding: 0.85rem 1.1rem 0.65rem;
}

.specification-header-main { display: flex; align-items: flex-start; gap: 0.55rem; }
.specification-header strong {
  display: block;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-soft);
}
.specification-toggle { font-size: 0.72rem; color: var(--text-soft); margin-top: 0.08rem; }
.specification-caption { display: block; margin-top: 0.18rem; color: var(--text-soft); font-size: 0.8rem; }
.specification-total {
  padding: 0;
  background: transparent;
  color: var(--accent);
  font-size: 1rem;
  font-weight: 700;
}

.specification-body {
  display: grid;
  grid-template-rows: auto minmax(12rem, 1fr) auto;
  gap: 0.55rem;
  min-height: 0;
  padding: 0 0.9rem 0.85rem;
}

.specification-toolbar { align-items: stretch; gap: 0.45rem; padding-top: 0.45rem; }
.toolbar-wrap { align-items: stretch; }
.filter-select { min-width: 9rem; }
.specification-toolbar-control {
  min-height: 2rem;
  font-size: 0.82rem;
}

.specification-toolbar-button {
  min-height: 2rem;
  border-radius: 6px;
  padding: 0.42rem 0.68rem;
  font-size: 0.8rem;
}

.empty-specification, .centered-state { border: 1px dashed var(--border); border-radius: 8px; color: var(--text-soft); padding: 0.95rem; text-align: center; }
.centered-state { min-height: 12rem; display: grid; place-items: center; }
.specification-empty { display: grid; min-height: 14rem; place-items: center; }
.specification-table-shell, .preview-table-shell { overflow: auto; min-height: 0; }
.specification-table-shell {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 8px;
  background: #ffffff;
}

.specification-table, .preview-table { width: 100%; border-collapse: collapse; }
.specification-table {
  min-width: 54rem;
  table-layout: fixed;
  font-size: 0.83rem;
}

.specification-col-type { width: 7.5rem; }
.specification-col-name { width: auto; }
.specification-col-unit { width: 6.5rem; }
.specification-col-rate { width: 6.75rem; }
.specification-col-price { width: 7.5rem; }
.specification-col-total { width: 7.5rem; }
.specification-col-actions { width: 3.25rem; }

.specification-table th,
.specification-table td,
.preview-table th,
.preview-table td {
  text-align: left;
  vertical-align: top;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border);
}

.specification-table th,
.preview-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  color: var(--text-soft);
  font-size: 0.69rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: rgba(248, 250, 252, 0.98);
}

.inline-control {
  min-width: 0;
  min-height: 1.85rem;
  border-radius: 4px;
  padding: 0.34rem 0.42rem;
  font-size: 0.82rem;
}

.name-cell { display: grid; gap: 0.25rem; }
.name-field-control { display: grid; gap: 0.25rem; }
.name-field-control-material { align-items: stretch; grid-template-columns: minmax(0, 1fr) 2.05rem; }
.name-field-input { width: 100%; }
.material-picker-button {
  min-width: 2.05rem;
  min-height: 1.85rem;
  padding-inline: 0;
  border-radius: 4px;
}
.field-hint { color: var(--text-soft); font-size: 0.73rem; }
.row-total { display: block; text-align: right; white-space: nowrap; font-weight: 700; font-size: 0.84rem; }
.row-error-strip td { padding-top: 0.1rem; color: var(--danger); font-size: 0.8rem; }

.spec-cell-type,
.spec-cell-unit,
.spec-cell-number,
.spec-cell-total,
.spec-cell-actions {
  white-space: nowrap;
}

.spec-cell-actions .table-actions {
  justify-content: flex-end;
}

.row-delete-button {
  min-width: 1.9rem;
  min-height: 1.85rem;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  box-shadow: none;
  line-height: 1;
  font-size: 0.95rem;
}

.totals-panel {
  border-top: 1px solid rgba(226, 232, 240, 0.95);
  padding-top: 0.7rem;
  display: grid;
  gap: 0.45rem;
}
.totals-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 0.75rem; }
.totals-header h3 {
  margin: 0;
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-soft);
}
.totals-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  justify-content: space-between;
}
.total-card {
  border: none;
  border-radius: 999px;
  background: #f8fafc;
  padding: 0.34rem 0.6rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.total-card strong { font-size: 0.86rem; }
.total-card-strong { background: rgba(59, 130, 246, 0.1); }
.modal-stack { display: grid; gap: 1rem; }
.copy-layout { display: grid; gap: 1rem; grid-template-columns: minmax(240px, 300px) minmax(0, 1fr); }
.copy-list { display: grid; gap: 0.5rem; max-height: 26rem; overflow-y: auto; }
.copy-source { border: 1px solid var(--border); border-radius: 16px; background: rgba(255, 255, 255, 0.7); padding: 0.85rem; text-align: left; display: grid; gap: 0.2rem; }
.copy-source.selected { border-color: var(--accent); background: var(--accent-ghost); }
.copy-preview { min-width: 0; }
.error-list { color: var(--danger); font-size: 0.88rem; }
.success-text { color: var(--success); font-size: 0.88rem; }
.material-list { display: grid; gap: 0.5rem; }
.material-item { border: 1px solid var(--border); border-radius: 16px; background: rgba(255, 255, 255, 0.78); padding: 0.9rem 1rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; text-align: left; flex: 1; }
.material-item-row { display: flex; gap: 0.5rem; align-items: stretch; }
.material-edit-button { flex-shrink: 0; min-width: 3.5rem; }
.material-edit-form { display: grid; grid-template-columns: 1fr 0.7fr 0.5fr 0.7fr auto auto; gap: 0.5rem; align-items: center; width: 100%; padding: 0.5rem; border: 1px solid var(--accent); border-radius: 16px; background: rgba(178, 76, 45, 0.04); }
.material-meta { display: grid; gap: 0.15rem; justify-items: end; white-space: nowrap; }
.material-meta-inline { display: grid; gap: 0.2rem; justify-items: end; white-space: nowrap; }
.pagination-row { justify-content: space-between; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

.unit-summary { border: 1px solid var(--border); border-radius: 18px; background: rgba(255, 255, 255, 0.7); padding: 1rem; display: grid; gap: 0.75rem; }
.unit-summary h4 { margin: 0; font-size: 1rem; }
.unit-stats { display: flex; gap: 1.5rem; align-items: center; }
.stat { display: flex; align-items: center; gap: 0.35rem; font-size: 0.95rem; }
.stat strong { font-size: 1.1rem; color: var(--accent); }
.stat-warning strong { color: #b27e2d; }
.missing-materials-list { display: grid; gap: 0.65rem; }
.missing-material-item { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; border: 1px solid var(--border); border-radius: 14px; background: rgba(255, 255, 255, 0.76); padding: 0.85rem 0.95rem; }
.new-units-warning { border-top: 1px solid var(--border); padding-top: 0.75rem; }
.warning-text { margin: 0 0 0.5rem; color: #7c5617; font-weight: 600; }
.warning-text-inline { color: #7c5617; font-size: 0.88rem; }
.new-units-list { margin: 0.5rem 0; padding-left: 1.5rem; color: #7c5617; }
.new-units-list li { margin: 0.25rem 0; }
.hint-text { margin: 0.5rem 0 0; color: var(--text-soft); font-size: 0.88rem; font-style: italic; }

.unit-cell { display: flex; align-items: center; gap: 0.5rem; }
.badge { display: inline-block; padding: 0.25rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }
.badge-success { background: rgba(45, 122, 68, 0.12); color: var(--success); }
.badge-warning { background: rgba(178, 126, 45, 0.12); color: #7c5617; }

.status-cell { display: grid; gap: 0.35rem; }
.warning-list { margin: 0.35rem 0 0; padding: 0; list-style: none; }
.warning-item { color: #7c5617; font-size: 0.82rem; margin: 0.15rem 0; }

@media (max-width: 1023px) {
  .copy-layout { grid-template-columns: 1fr; }
  .work-basic-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .work-field-span-4,
  .work-field-span-3,
  .work-field-span-2 { grid-column: span 2; }
  .work-field-span-1 { grid-column: span 1; }
  .work-review-grid { grid-template-columns: 1fr; }
  .specification-header { align-items: flex-start; flex-direction: column; }
  .specification-table { min-width: 52rem; }
}

@media (max-width: 767px) {
  .work-topbar,
  .work-topbar-main,
  .work-topbar-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .work-main-panel-body,
  .specification-body { padding: 0.85rem; }
  .work-basic-grid { grid-template-columns: 1fr; }
  .work-field-span-4,
  .work-field-span-2,
  .work-field-span-3,
  .work-field-span-1 { grid-column: span 1; }
  .work-review-head,
  .totals-header,
  .work-topbar-actions { flex-direction: row; }
  .specification-header { align-items: flex-start; flex-direction: column; }
  .specification-table { min-width: 48rem; }
  .specification-table th,
  .specification-table td,
  .preview-table th,
  .preview-table td { padding: 0.5rem; }
  .material-item { flex-direction: column; align-items: stretch; }
  .material-meta { justify-items: start; }
  .material-meta-inline { justify-items: start; }
  .unit-stats { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
  .unit-cell { flex-direction: column; align-items: flex-start; }
  .missing-material-item { flex-direction: column; }
  .name-field-control-material { grid-template-columns: minmax(0, 1fr); }
}
</style>
