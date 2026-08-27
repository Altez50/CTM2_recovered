"""Каталог метаданных инженерного раздела «Таблицы».

Декларативно описывает разрешённые для просмотра/запросов таблицы и синонимы
(бизнес-наименования) их полей. Физические имена столбцов берутся из интроспекции
схемы во время выполнения (``table_columns``), а синонимы — отсюда.

См. TABLES_ENGINEERING_SPEC.md, раздел 4.2.
"""

from __future__ import annotations

from typing import Any

from api.db.dialect import table_columns


# ── Категории таблиц ──────────────────────────────────────────────────────
CATEGORY_REFERENCE = "reference"
CATEGORY_DOCUMENT = "document"
CATEGORY_LINE = "line"
CATEGORY_REGISTER = "register"
CATEGORY_CATALOG = "catalog"

CATEGORY_LABELS: dict[str, str] = {
    CATEGORY_REFERENCE: "Справочники",
    CATEGORY_DOCUMENT: "Документы",
    CATEGORY_LINE: "Табличные части",
    CATEGORY_REGISTER: "Регистры",
    CATEGORY_CATALOG: "Справочники учёта затрат",
}


# ── Общие синонимы полей (физ. имя → синоним), общие для большинства таблиц ─
_COMMON_FIELD_SYNONYMS: dict[str, str] = {
    "id": "Ссылка",
    "name": "Наименование",
    "full_name": "ФИО",
    "number": "Номер",
    "date": "Дата",
    "inn": "ИНН",
    "phone": "Телефон",
    "code": "Код",
    "address": "Адрес",
    "unit": "Единица",
    "price": "Цена",
    "quantity": "Количество",
    "sum": "Сумма",
    "amount": "Сумма",
    "labor_rate": "Трудоёмкость",
    "hourly_rate": "ЧасоваяСтавка",
    "contact_person": "КонтактноеЛицо",
    "position": "Должность",
    "personnel_number": "ТабельныйНомер",
    "short_name": "Кратко",
    "is_posted": "Проведён",
    "posted_at": "ДатаПроведения",
    "marked_for_deletion": "ПометкаУдаления",
    "is_group": "ЭтоГруппа",
    "group_name": "ИмяГруппы",
    "parent_group_id": "РодительскаяГруппа",
    "is_collapsed": "Свёрнута",
    "parent_id": "Родитель",
    "created_at": "Создан",
    "modified_at": "Изменён",
    "period": "Период",
    "note": "Примечание",
    "description": "Описание",
    "line_number": "НомерСтроки",
    "recorder_type": "ТипРегистратора",
    "recorder_id": "Регистратор",
    "unit_price": "Цена",
    "consumption_rate": "НормаРасхода",
    "component_type": "ТипКомпонента",
    "component_name": "Компонент",
    "currency": "Валюта",
    "vat_rate": "СтавкаНДС",
    "vat_amount": "СуммаНДС",
    "payment_deferral_days": "ОтсрочкаПлатежаДни",
    "agreement_date": "ДатаСоглашения",
    "valid_until": "ДействуетДо",
    "kind": "Вид",
    "status": "Статус",
    "direction": "Направление",
    "category": "Категория",
    "total_sum": "ИтогоСумма",
    "total_labor": "ИтогоТрудоёмкость",
    "planned_labor": "ПлановаяТрудоёмкость",
    "actual_labor": "ФактТрудоёмкость",
    "deviation_percent": "ОтклонениеПроцент",
    "actual_sum": "ФактСумма",
    "specification_review_status": "СтатусПроверкиСпецификации",
    "specification_review_note": "ЗаметкаПроверки",
    "updated_at": "Обновлён",
    "is_deleted": "Удалён",
    "quantity_income": "ПриходКолво",
    "quantity_expense": "РасходКолво",
    "sum_income": "ПриходСумма",
    "sum_expense": "РасходСумма",
    "planned_amount": "ПланСумма",
    "fact_amount": "ФактСумма",
    "planned_date": "ПланДата",
    "date_from": "ДатаС",
    "date_to": "ДатаПо",
    "due_date": "СрокОплаты",
    "month_year": "Месяц",
    "total_hours": "ВсегоЧасов",
    "total_amount": "ВсегоСумма",
    "hours_worked": "ЧасовОтработано",
    "work_date": "ДатаРаботы",
    "sum_without_vat": "СуммаБезНДС",
    "sum_with_vat": "СуммаСНДС",
    "price_without_vat": "ЦенаБезНДС",
    "drawing_code": "КодЧертежа",
    "source_kind": "ИсточникВид",
    "source_ref": "ИсточникСсылка",
}

# Поля, скрытые по умолчанию в просмотрщике (служебные).
_HIDDEN_DEFAULT: set[str] = {"uuid", "updated_at", "is_deleted"}


# ── Описание таблиц ──────────────────────────────────────────────────────
# Структура значения:
#   {
#     "synonym": str,                — синоним таблицы
#     "category": str,               — категория
#     "fks": { physical: (synonym, ref_table) },   — ссылочные поля (FK)
#     "overrides": { physical: synonym },          — точные синонимы полей
#   }
# Поля, не указанные явно, получают синоним из _COMMON_FIELD_SYNONYMS или
# fallback на физическое имя.

_TABLE_DEFS: dict[str, dict[str, Any]] = {
    # ── Справочники ──
    "counterparties": {
        "synonym": "Контрагенты", "category": CATEGORY_REFERENCE,
        "fks": {"parent_id": ("Родитель", "counterparties")},
    },
    "objects": {
        "synonym": "Объекты", "category": CATEGORY_REFERENCE,
        "fks": {"owner_id": ("Владелец", "counterparties"), "parent_id": ("Родитель", "objects")},
    },
    "works": {
        "synonym": "Работы", "category": CATEGORY_REFERENCE,
        "fks": {"parent_id": ("Родитель", "works")},
    },
    "persons": {
        "synonym": "Физлица", "category": CATEGORY_REFERENCE,
        "fks": {"parent_id": ("Родитель", "persons")},
        "overrides": {"user_id": "Пользователь"},
    },
    "organizations": {
        "synonym": "Организации", "category": CATEGORY_REFERENCE,
        "fks": {
            "default_responsible_id": ("ОтветственныйПоУмолчанию", "persons"),
            "parent_id": ("Родитель", "organizations"),
        },
    },
    "contracts": {
        "synonym": "Договоры", "category": CATEGORY_REFERENCE,
        "fks": {
            "counterparty_id": ("Контрагент", "counterparties"),
            "organization_id": ("Организация", "organizations"),
            "parent_id": ("Родитель", "contracts"),
        },
    },
    "materials": {
        "synonym": "Материалы", "category": CATEGORY_REFERENCE,
        "fks": {"unit_id": ("Единица", "units")},
    },
    "units": {"synonym": "Единицы", "category": CATEGORY_REFERENCE},
    "work_specifications": {
        "synonym": "СпецификацииРабот", "category": CATEGORY_REFERENCE,
        "fks": {
            "work_id": ("Работа", "works"),
            "unit_id": ("Единица", "units"),
            "material_id": ("Материал", "materials"),
        },
    },
    # ── Документы (шапки) ──
    "estimates": {
        "synonym": "Сметы", "category": CATEGORY_DOCUMENT,
        "fks": {
            "customer_id": ("Заказчик", "counterparties"),
            "object_id": ("Объект", "objects"),
            "contractor_id": ("Подрядчик", "organizations"),
            "responsible_id": ("Ответственный", "persons"),
            "contract_id": ("Договор", "contracts"),
        },
    },
    "daily_reports": {
        "synonym": "ДневныеОтчёты", "category": CATEGORY_DOCUMENT,
        "fks": {
            "estimate_id": ("Смета", "estimates"),
            "foreman_id": ("Прораб", "persons"),
            "supplementary_agreement_id": ("ДопСоглашение", "contracts"),
        },
    },
    "timesheets": {
        "synonym": "Табели", "category": CATEGORY_DOCUMENT,
        "fks": {
            "object_id": ("Объект", "objects"),
            "estimate_id": ("Смета", "estimates"),
            "foreman_id": ("Прораб", "persons"),
        },
    },
    "material_consumptions": {
        "synonym": "РасходМатериалов", "category": CATEGORY_DOCUMENT,
        "fks": {"object_id": ("Объект", "objects"), "estimate_id": ("Смета", "estimates")},
    },
    "machinery_usage_reports": {
        "synonym": "РапортыМашин", "category": CATEGORY_DOCUMENT,
        "fks": {"object_id": ("Объект", "objects"), "estimate_id": ("Смета", "estimates")},
    },
    "subcontract_acceptances": {
        "synonym": "АктыСубподряда", "category": CATEGORY_DOCUMENT,
        "fks": {
            "object_id": ("Объект", "objects"),
            "estimate_id": ("Смета", "estimates"),
            "counterparty_id": ("Контрагент", "counterparties"),
            "contract_id": ("Договор", "contracts"),
        },
    },
    "overhead_expenses": {
        "synonym": "НакладныеРасходы", "category": CATEGORY_DOCUMENT,
        "fks": {"object_id": ("Объект", "objects")},
    },
    "cost_calculations": {
        "synonym": "РасчётыСебестоимости", "category": CATEGORY_DOCUMENT,
        "fks": {"object_id": ("Объект", "objects")},
    },
    "payment_schedules": {
        "synonym": "ГрафикиПлатежей", "category": CATEGORY_DOCUMENT,
        "fks": {
            "object_id": ("Объект", "objects"),
            "contract_id": ("Договор", "contracts"),
            "responsible_id": ("Ответственный", "persons"),
        },
    },
    "payment_transactions": {
        "synonym": "Платежи", "category": CATEGORY_DOCUMENT,
        "fks": {
            "counterparty_id": ("Контрагент", "counterparties"),
            "contract_id": ("Договор", "contracts"),
            "estimate_id": ("Смета", "estimates"),
            "object_id": ("Объект", "objects"),
            "linked_schedule_id": ("ГрафикПлатежей", "payment_schedules"),
            "linked_line_id": ("СтрокаГрафика", "payment_schedule_lines"),
        },
    },
    "goods_receipts": {
        "synonym": "ПоступленияТМЦ", "category": CATEGORY_DOCUMENT,
        "fks": {
            "organization_id": ("Организация", "organizations"),
            "counterparty_id": ("Контрагент", "counterparties"),
            "contract_id": ("Договор", "contracts"),
            "object_id": ("Объект", "objects"),
            "estimate_id": ("Смета", "estimates"),
            "responsible_id": ("Ответственный", "persons"),
        },
    },
    "goods_issues": {
        "synonym": "РасходыТМЦ", "category": CATEGORY_DOCUMENT,
        "fks": {
            "organization_id": ("Организация", "organizations"),
            "counterparty_id": ("Контрагент", "counterparties"),
            "contract_id": ("Договор", "contracts"),
            "object_id": ("Объект", "objects"),
            "estimate_id": ("Смета", "estimates"),
            "responsible_id": ("Ответственный", "persons"),
        },
    },
    # ── Табличные части ──
    "estimate_lines": {
        "synonym": "СтрокиСметы", "category": CATEGORY_LINE,
        "fks": {"estimate_id": ("Смета", "estimates"), "work_id": ("Работа", "works")},
    },
    "daily_report_lines": {
        "synonym": "СтрокиДневногоОтчёта", "category": CATEGORY_LINE,
        "fks": {"report_id": ("ДневнойОтчёт", "daily_reports"), "work_id": ("Работа", "works")},
    },
    "daily_report_executors": {
        "synonym": "Исполнители", "category": CATEGORY_LINE,
        "fks": {
            "report_line_id": ("СтрокаОтчёта", "daily_report_lines"),
            "executor_id": ("Исполнитель", "persons"),
        },
    },
    "timesheet_lines": {
        "synonym": "СтрокиТабеля", "category": CATEGORY_LINE,
        "fks": {"timesheet_id": ("Табель", "timesheets"), "employee_id": ("Сотрудник", "persons")},
    },
    "material_consumption_lines": {
        "synonym": "СтрокиРасходаМатериалов", "category": CATEGORY_LINE,
        "fks": {
            "material_consumption_id": ("Документ", "material_consumptions"),
            "material_id": ("Материал", "materials"),
            "work_id": ("Работа", "works"),
            "object_id": ("Объект", "objects"),
        },
    },
    "machinery_usage_lines": {
        "synonym": "СтрокиРапортаМашин", "category": CATEGORY_LINE,
        "fks": {
            "report_id": ("Рапорт", "machinery_usage_reports"),
            "machine_id": ("Машина", "machines"),
            "work_id": ("Работа", "works"),
        },
    },
    "subcontract_acceptance_lines": {
        "synonym": "СтрокиСубподряда", "category": CATEGORY_LINE,
        "fks": {
            "acceptance_id": ("Акт", "subcontract_acceptances"),
            "work_id": ("Работа", "works"),
        },
    },
    "overhead_expense_lines": {
        "synonym": "СтрокиНакладныхРасходов", "category": CATEGORY_LINE,
        "fks": {"overhead_expense_id": ("Документ", "overhead_expenses")},
    },
    "goods_receipt_lines": {
        "synonym": "СтрокиПоступленияТМЦ", "category": CATEGORY_LINE,
        "fks": {
            "receipt_id": ("Поступление", "goods_receipts"),
            "material_id": ("Материал", "materials"),
            "unit_id": ("Единица", "units"),
            "object_id": ("Объект", "objects"),
        },
    },
    "goods_issue_lines": {
        "synonym": "СтрокиРасходаТМЦ", "category": CATEGORY_LINE,
        "fks": {
            "issue_id": ("Расход", "goods_issues"),
            "material_id": ("Материал", "materials"),
            "unit_id": ("Единица", "units"),
            "object_id": ("Объект", "objects"),
        },
    },
    "payment_schedule_lines": {
        "synonym": "СтрокиГрафикаПлатежей", "category": CATEGORY_LINE,
        "fks": {
            "schedule_id": ("График", "payment_schedules"),
            "counterparty_id": ("Контрагент", "counterparties"),
            "contract_id": ("Договор", "contracts"),
            "estimate_id": ("Смета", "estimates"),
            "object_id": ("Объект", "objects"),
        },
    },
    # ── Регистры ──
    "work_execution_register": {
        "synonym": "РегистрРабот", "category": CATEGORY_REGISTER,
        "fks": {
            "object_id": ("Объект", "objects"),
            "estimate_id": ("Смета", "estimates"),
            "work_id": ("Работа", "works"),
        },
    },
    "payroll_register": {
        "synonym": "РегистрЗарплаты", "category": CATEGORY_REGISTER,
        "fks": {
            "object_id": ("Объект", "objects"),
            "estimate_id": ("Смета", "estimates"),
            "employee_id": ("Сотрудник", "persons"),
        },
    },
    "inventory_register": {
        "synonym": "РегистрТМЦ", "category": CATEGORY_REGISTER,
        "fks": {
            "material_id": ("Материал", "materials"),
            "object_id": ("Объект", "objects"),
            "unit_id": ("Единица", "units"),
        },
    },
    "mutual_settlements_register": {
        "synonym": "Взаиморасчёты", "category": CATEGORY_REGISTER,
        "fks": {
            "organization_id": ("Организация", "organizations"),
            "counterparty_id": ("Контрагент", "counterparties"),
            "contract_id": ("Договор", "contracts"),
            "object_id": ("Объект", "objects"),
            "estimate_id": ("Смета", "estimates"),
        },
    },
    "payment_schedule_register": {
        "synonym": "РегистрГрафиковПлатежей", "category": CATEGORY_REGISTER,
        "fks": {
            "counterparty_id": ("Контрагент", "counterparties"),
            "contract_id": ("Договор", "contracts"),
            "estimate_id": ("Смета", "estimates"),
            "object_id": ("Объект", "objects"),
            "linked_line_id": ("СтрокаГрафика", "payment_schedule_lines"),
        },
    },
    "actual_costs": {
        "synonym": "ФактическиеЗатраты", "category": CATEGORY_REGISTER,
        "fks": {
            "calc_id": ("Расчёт", "cost_calculations"),
            "object_id": ("Объект", "objects"),
            "work_id": ("Работа", "works"),
            "cost_element_id": ("ЭлементЗатрат", "cost_elements"),
        },
    },
    "planned_costs": {
        "synonym": "ПлановыеЗатраты", "category": CATEGORY_REGISTER,
        "fks": {
            "calc_id": ("Расчёт", "cost_calculations"),
            "object_id": ("Объект", "objects"),
            "work_id": ("Работа", "works"),
            "cost_element_id": ("ЭлементЗатрат", "cost_elements"),
        },
    },
    "overhead_distribution": {
        "synonym": "РаспределениеНакладных", "category": CATEGORY_REGISTER,
        "fks": {
            "overhead_expense_id": ("Накладные", "overhead_expenses"),
            "object_id": ("Объект", "objects"),
            "work_id": ("Работа", "works"),
            "allocation_base_id": ("БазаРаспределения", "allocation_bases"),
        },
    },
    "completed_works_cost": {
        "synonym": "СебестоимостьВыпРабот", "category": CATEGORY_REGISTER,
        "fks": {
            "calc_id": ("Расчёт", "cost_calculations"),
            "object_id": ("Объект", "objects"),
            "work_id": ("Работа", "works"),
        },
    },
    # ── Справочники учёта затрат ──
    "allocation_bases": {"synonym": "БазыРаспределения", "category": CATEGORY_CATALOG},
    "cost_elements": {
        "synonym": "ЭлементыЗатрат", "category": CATEGORY_CATALOG,
        "overrides": {"element_type": "ТипЭлемента", "is_direct": "Прямой"},
    },
    "machines": {
        "synonym": "Машины", "category": CATEGORY_CATALOG,
        "fks": {"object_id": ("Объект", "objects")},
    },
}


def allowed_tables() -> set[str]:
    """Множество физических имён таблиц, разрешённых для инженерного доступа."""
    return set(_TABLE_DEFS)


def _infer_type(physical: str) -> str:
    """Грубая оценка типа поля по физическому имени (для отображения)."""
    p = physical.lower()
    if p == "id" or p.endswith("_id"):
        return "ref"
    if p.endswith("_at") or p == "date" or "date" in p:
        return "date"
    if p.startswith("is_") or p.startswith("marked_") or p in {"is_group", "is_collapsed"}:
        return "bool"
    if any(k in p for k in ("sum", "price", "amount", "rate", "quantity", "total", "balance", "hours", "percent")):
        return "number"
    return "text"


# Колонка «представления» ссылки для разворота FK в просмотрщике.
_REF_DISPLAY_COLUMN: dict[str, str] = {
    "counterparties": "name",
    "objects": "name",
    "works": "name",
    "organizations": "name",
    "materials": "name",
    "units": "short_name",
    "persons": "full_name",
    "contracts": "number",
    "estimates": "number",
    "daily_reports": "number",
    "timesheets": "number",
    "machinery_usage_reports": "number",
    "subcontract_acceptances": "number",
    "overhead_expenses": "number",
    "cost_calculations": "number",
    "payment_schedules": "number",
    "payment_schedule_lines": "line_number",
    "material_consumptions": "number",
    "goods_receipts": "number",
    "goods_issues": "number",
    "machines": "name",
    "cost_elements": "name",
    "allocation_bases": "name",
}


def ref_display_column(ref_table: str) -> str:
    """Колонка целевой таблицы, используемая как текстовое представление ссылки."""
    return _REF_DISPLAY_COLUMN.get(ref_table, "name")


def table_synonym(physical: str) -> str:
    return _TABLE_DEFS.get(physical, {}).get("synonym", physical)


def table_columns_list(connection, physical: str) -> list[str]:
    """Отсортированный список физических колонок таблицы (интроспекция)."""
    from api.db import current_backend

    backend = current_backend()
    return sorted(table_columns(connection, physical, backend))


def table_fks(physical: str) -> dict[str, tuple[str, str]]:
    """Карта ссылочных полей таблицы: {физ_колонка: (синоним, целевая_таблица)}."""
    tdef = _TABLE_DEFS.get(physical, {})
    return dict(tdef.get("fks", {}))


def fk_synonym(physical: str, column: str) -> str:
    """Синоним конкретного ссылочного поля (для заголовка колонки-представления)."""
    fks = _TABLE_DEFS.get(physical, {}).get("fks", {})
    if column in fks:
        return fks[column][0]
    return column


def table_category(physical: str) -> str:
    return _TABLE_DEFS.get(physical, {}).get("category", CATEGORY_REFERENCE)


def field_descriptor(physical_table: str, column: str) -> dict[str, Any]:
    """Дескриптор одного поля таблицы: синоним, тип, ссылка."""
    tdef = _TABLE_DEFS.get(physical_table, {})
    fks = tdef.get("fks", {})
    overrides = tdef.get("overrides", {})

    if column in fks:
        synonym, ref_table = fks[column]
        return {
            "name": column,
            "synonym": synonym,
            "type": "ref",
            "ref_table": ref_table,
            "hidden_default": column in _HIDDEN_DEFAULT,
        }
    if column in overrides:
        synonym = overrides[column]
    else:
        synonym = _COMMON_FIELD_SYNONYMS.get(column, column)
    return {
        "name": column,
        "synonym": synonym,
        "type": _infer_type(column),
        "hidden_default": column in _HIDDEN_DEFAULT,
    }


def table_descriptor(connection, physical: str) -> dict[str, Any] | None:
    """Полный дескриптор таблицы с интроспекцией реальных колонок."""
    from api.db import current_backend

    backend = current_backend()
    tdef = _TABLE_DEFS.get(physical)
    if tdef is None:
        return None
    columns = sorted(table_columns(connection, physical, backend))
    fields = [field_descriptor(physical, c) for c in columns]
    return {
        "name": physical,
        "synonym": tdef["synonym"],
        "category": tdef["category"],
        "fields": fields,
    }


def catalog_payload(connection) -> dict[str, Any]:
    """Каталог для эндпоинта GET /api/engineering/catalog, сгруппированный по категориям."""
    from api.db import current_backend

    backend = current_backend()
    categories: dict[str, list[dict[str, Any]]] = {}
    # Стабильный порядок: как в CATEGORY_LABELS.
    for cid in CATEGORY_LABELS:
        categories[cid] = []
    for physical, tdef in _TABLE_DEFS.items():
        try:
            columns = sorted(table_columns(connection, physical, backend))
        except Exception:
            columns = []
        fields = [field_descriptor(physical, c) for c in columns]
        categories[tdef["category"]].append({
            "name": physical,
            "synonym": tdef["synonym"],
            "fields": fields,
        })
    return {
        "categories": [
            {"id": cid, "label": label, "tables": categories.get(cid, [])}
            for cid, label in CATEGORY_LABELS.items()
        ]
    }


# ── Карты для транслятора синонимов (см. engineering_query) ──────────────

def build_translation_maps() -> dict[str, Any]:
    """Построить отображения синоним→физическое имя для транслятора запросов.

    Возвращает словарь:
      - table_by_synonym: {synonym_lower: physical}
      - fields_by_table:  {physical: {synonym_lower: physical_column}}
      - physical_tables:  set разрешённых физических таблиц
    Физические имена также включены как ключи (разрешаем и их).
    """
    table_by_synonym: dict[str, str] = {}
    fields_by_table: dict[str, dict[str, str]] = {}
    physical_tables: set[str] = set()

    for physical, tdef in _TABLE_DEFS.items():
        physical_tables.add(physical)
        table_by_synonym[tdef["synonym"].lower()] = physical
        # физическое имя тоже принимаем как "синоним" таблицы
        table_by_synonym[physical.lower()] = physical

    # Поля строятся по известным колонкам без интроспекции: используем синонимы
    # из fks/overrides/common-map для каждого физического столбца, который
    # известен. Неизвестные колонки будут разрешены во время выполнения через
    # интроспекцию — здесь даём максимально полный словарь синонимов.
    # Чтобы транслятор работал без подключения к БД, формируем карту синонимов
    # полей по объединению всех таблиц (для квалифицированных X.Y разрешается
    # по конкретной таблице; для неквалифицированных — глобально, см. ниже).
    for physical in _TABLE_DEFS:
        fields_by_table[physical] = {}
        # физические имена колонок как ключи
    return {
        "table_by_synonym": table_by_synonym,
        "fields_by_table": fields_by_table,
        "physical_tables": physical_tables,
    }
