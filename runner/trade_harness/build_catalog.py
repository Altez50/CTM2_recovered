"""Authoring source for trade scenarios; numeric expectations are explicit, not app-derived."""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
AREAS = {
    "master": ("НСИ и аналитики", "Администрирование", ["Catalog.Организации", "Catalog.Контрагенты", "Catalog.ДоговорыКонтрагентов", "Catalog.Номенклатура", "Catalog.Склады"]),
    "procurement": ("Закупки", "Закупки", ["Document.ЗаказПоставщику", "Document.ПриобретениеТоваровУслуг", "AccumulationRegister.РасчетыСПоставщиками"]),
    "sales": ("Оптовые продажи", "Продажи", ["Document.ЗаказКлиента", "Document.РеализацияТоваровУслуг", "AccumulationRegister.РасчетыСКлиентами"]),
    "availability": ("Заказы, обеспечение и резервы", "Склад", ["Document.ЗаказКлиента", "Document.ЗаказПоставщику", "AccumulationRegister.ЗапасыИПотребности", "AccumulationRegister.РезервыТоваровОрганизаций"]),
    "warehouse": ("Склад и инвентаризация", "Склад", ["Document.ПеремещениеТоваров", "Document.ПересчетТоваров", "Document.ОприходованиеИзлишковТоваров", "Document.СписаниеНедостачТоваров", "AccumulationRegister.ТоварыНаСкладах"]),
    "returns": ("Возвраты и корректировки", "Продажи", ["Document.ВозвратТоваровОтКлиента", "Document.ВозвратТоваровПоставщику", "Document.КорректировкаРеализации", "Document.КорректировкаПриобретения"]),
    "payments": ("Оплаты и задолженность", "Казначейство", ["Document.ПоступлениеБезналичныхДенежныхСредств", "Document.СписаниеБезналичныхДенежныхСредств", "AccumulationRegister.РасчетыСКлиентами", "AccumulationRegister.РасчетыСПоставщиками"]),
    "treasury": ("Банк, касса и планирование денег", "Казначейство", ["Document.ПриходныйКассовыйОрдер", "Document.РасходныйКассовыйОрдер", "Document.ЗаявкаНаРасходованиеДенежныхСредств", "AccumulationRegister.ДенежныеСредстваНаличные", "AccumulationRegister.ДенежныеСредстваБезналичные"]),
    "pricing": ("Цены, скидки и соглашения", "CRMИМаркетинг", ["Document.УстановкаЦенНоменклатуры", "Document.РегистрацияЦенНоменклатурыПоставщика", "Catalog.СоглашенияСКлиентами", "Catalog.СоглашенияСПоставщиками"]),
    "cost": ("Себестоимость и финансовый результат", "ФинансовыйРезультатИКонтроллинг", ["Document.РасчетСебестоимостиТоваров", "Document.РаспределениеПрочихЗатрат", "AccumulationRegister.СебестоимостьТоваров", "AccumulationRegister.ВыручкаИСебестоимостьПродаж"]),
    "vat_currency": ("НДС, валюты и импорт", "ФинансовыйРезультатИКонтроллинг", ["Document.СчетФактураПолученный", "Document.СчетФактураВыданный", "Document.ТаможеннаяДекларацияИмпорт", "Document.РасчетКурсовыхРазниц"]),
    "retail": ("Розница и лояльность", "Продажи", ["Document.ЧекККМ", "Document.ЧекККМВозврат", "Document.ОтчетОРозничныхПродажах", "Document.ОтчетБанкаПоОперациямЭквайринга"]),
    "commission": ("Комиссия, хранение и тара", "Продажи", ["Document.ОтчетКомиссионера", "Document.ОтчетКомитенту", "Document.ПередачаТоваровХранителю", "AccumulationRegister.ТоварыПереданныеНаКомиссию", "AccumulationRegister.ПринятаяВозвратнаяТара"]),
    "intercompany": ("Межфирменный учет", "Склад", ["Document.ПередачаТоваровМеждуОрганизациями", "Document.ВозвратТоваровМеждуОрганизациями"]),
    "assembly": ("Сборка, разборка и внутреннее потребление", "Склад", ["Document.ЗаказНаСборку", "Document.СборкаТоваров", "Document.ВнутреннееПотребление"]),
    "planning": ("Планирование закупок и продаж", "Планирование", ["Document.ПланПродаж", "Document.ПланЗакупок", "Document.ПланОстатков"]),
    "reports": ("Отчеты и сверки", "ОтчетыБазовая", ["AccumulationRegister.ТоварыНаСкладах", "AccumulationRegister.РасчетыСКлиентами", "AccumulationRegister.РасчетыСПоставщиками", "AccumulationRegister.ВыручкаИСебестоимостьПродаж"]),
    "lifecycle": ("Жизненный цикл и контроль", "Администрирование", ["Document.ПриобретениеТоваровУслуг", "Document.РеализацияТоваровУслуг", "Document.ПеремещениеТоваров"]),
    "integration": ("Обмен, маркировка и электронные документы", "ЭлектронноеВзаимодействие", ["Document.ЭлектронныйДокументИсходящийЭДО", "Document.ПриемкаТоваровИСМП", "Document.ТТНВходящаяЕГАИС", "Document.ТранспортнаяНакладная"]),
    "crm": ("CRM, коммерческие предложения и претензии", "CRMИМаркетинг", ["Document.КоммерческоеПредложениеКлиенту", "Document.ЗапросКоммерческихПредложенийПоставщиков", "Document.КоммерческоеПредложениеПоставщика", "Catalog.СделкиСКлиентами", "Catalog.Претензии"]),
    "logistics": ("Доставка и распоряжения", "Склад", ["Document.ЗаданиеНаПеревозку", "Document.ПоручениеЭкспедитору", "Document.ТранспортнаяНакладная", "Document.ЗаказНаПеремещение"]),
    "marketplace": ("Маркетплейсы и торговые представители", "Продажи", ["Document.ЗаказКлиента", "Document.ОтчетКомиссионера", "Document.ВозвратТоваровОтКлиента"]),
}
SCENARIOS = []


def add(ident, area, title, steps, *, adapter=None, preconditions=None, priority="P1", objects=None, profile="core"):
    SCENARIOS.append({"id": ident, "area": area, "title": title, "priority": priority, "profile": profile,
                      "preconditions": preconditions or ["Новая изолированная база; фикстура trade-v1; рубли; без оплат и начальных остатков"],
                      "ut_objects": objects or AREAS[area][2], "steps": steps,
                      "execution": {"ctm": adapter, "ut": None,
                                    "blocker": None if adapter else "Нет исполняемого адаптера CTM для этого бизнес-контракта; наличие API не доказывает поддержку"},
                      "oracle": {"type": "authored-business-contract", "ut_verified": False},
                      "dimensions": ["organization", "counterparty", "contract", "warehouse", "material"]})


def state(debts, stock, **extra):
    return {"debts": debts, "stock": stock, **extra}


def goods(kind, ref, quantity, price=100, **extra):
    return {"op": kind, "ref": ref, "quantity": quantity, "price": price, **extra}


def receipt(**extra):
    return goods("receipt", "r", 10, date="2026-10-01", **extra)


def issue(**extra):
    return goods("issue", "s", 3, 150, **extra)


def executable(ident, area, title, steps):
    add(ident, area, title, steps, adapter="api-v1", priority="P0")


BASE = state({"AX1": [1200, 0]}, {"A1": [10, 1000]})
SOLD = state({"AX1": [1200, 540]}, {"A1": [7, 700]})
EMPTY = state({}, {})
executable("PUR-001", "procurement", "Поступление с НДС и кредиторской задолженностью", [receipt(expect=BASE)])
executable("PUR-002", "procurement", "Черновик поступления не влияет на учет", [receipt(post=False, expect=state({}, {}, movements={"r": {"inventory": 0, "settlements": 0}}))])
executable("PUR-003", "procurement", "Два поступления с разными ценами", [goods("receipt", "r1", 3, 100), goods("receipt", "r2", 2, 200, expect=state({"AX1": [840, 0]}, {"A1": [5, 700]}))])
executable("PUR-004", "procurement", "Дробное количество и закупка без НДС", [goods("receipt", "r", 2.5, 80, vat=0, expect=state({"AX1": [200, 0]}, {"A1": [2.5, 200]}))])
executable("SAL-001", "sales", "Продажа списывает закупочную стоимость и начисляет долг по продажной", [receipt(expect=BASE), issue(expect=SOLD)])
executable("SAL-002", "sales", "Продажа без НДС", [receipt(vat=0), issue(vat=0, expect=state({"AX1": [1000, 450]}, {"A1": [7, 700]}))])
executable("SAL-003", "sales", "Нехватка товара: проведение атомарно отклоняется", [goods("receipt", "r", 2), issue(post_status=400, expect=state({"AX1": [240, 0]}, {"A1": [2, 200]}, movements={"s": {"inventory": 0, "settlements": 0}}))])
executable("SAL-004", "sales", "Черновик продажи не создает долг и списание", [receipt(), issue(post=False, expect=BASE)])
executable("SAL-005", "sales", "Частичные отгрузки суммируются", [receipt(), goods("issue", "s1", 2, 150), goods("issue", "s2", 1, 150, expect=SOLD)])
executable("WH-001", "warehouse", "Перемещение сохраняет общую стоимость и задолженность", [receipt(), {"op": "transfer", "ref": "t", "quantity": 4, "expect": state({"AX1": [1200, 0]}, {"A1": [6, 600], "A2": [4, 400]})}])
executable("WH-002", "warehouse", "Недостаток на складе отправителе", [receipt(), {"op": "transfer", "ref": "t", "quantity": 11, "post_status": 400, "expect": BASE}])
executable("WH-003", "warehouse", "Отмена перемещения восстанавливает склад источника", [receipt(), {"op": "transfer", "ref": "t", "quantity": 4}, {"op": "unpost", "ref": "t", "expect": BASE}])
executable("PAY-001", "payments", "Частичная оплата поставщику", [receipt(), {"op": "payment", "ref": "p", "direction": "outgoing", "amount": 500, "expect": state({"AX1": [700, 0]}, {"A1": [10, 1000]})}])
executable("PAY-002", "payments", "Частичная оплата от покупателя", [receipt(), issue(), {"op": "payment", "ref": "p", "direction": "incoming", "amount": 200, "expect": state({"AX1": [1200, 340]}, {"A1": [7, 700]})}])
executable("PAY-003", "payments", "Полное погашение обоих направлений", [receipt(), issue(), {"op": "payment", "ref": "p1", "direction": "outgoing", "amount": 1200}, {"op": "payment", "ref": "p2", "direction": "incoming", "amount": 540, "expect": state({}, {"A1": [7, 700]})}])
executable("PAY-004", "payments", "Отмена оплаты восстанавливает долг", [receipt(), {"op": "payment", "ref": "p", "direction": "outgoing", "amount": 500}, {"op": "unpost", "ref": "p", "expect": BASE}])
executable("PAY-005", "payments", "Оплата по одному договору не погашает другой", [receipt(), goods("receipt", "r2", 5, contract="AX2"), {"op": "payment", "ref": "p", "direction": "outgoing", "amount": 500, "expect": state({"AX1": [700, 0], "AX2": [600, 0]}, {"A1": [15, 1500]})}])
executable("PAY-006", "payments", "Организация платежа определяется своим договором", [receipt(), goods("receipt", "r2", 5, contract="BX1"), {"op": "payment", "ref": "p", "contract": "BX1", "direction": "outgoing", "amount": 200, "expect": state({"AX1": [1200, 0], "BX1": [400, 0]}, {"A1": [10, 1000], "B1": [5, 500]})}])
executable("COST-001", "cost", "Списание по средней при двух партиях", [goods("receipt", "r1", 10, 100), goods("receipt", "r2", 10, 200), goods("issue", "s", 4, 250, expect=state({"AX1": [3600, 1200]}, {"A1": [16, 2400]}))])
executable("REP-001", "reports", "ОСВ: входящее сальдо и обороты разных дней", [receipt(), issue(expect={**SOLD, "turnover": {"from": "2026-10-02", "to": "2026-10-02", "contract": "AX1", "values": {"payable_opening": 1200, "payable_accrual_turnover": 0, "payable_closing": 1200, "receivable_opening": 0, "receivable_accrual_turnover": 540, "receivable_closing": 540}}})])
executable("LIFE-001", "lifecycle", "Повторное проведение поступления не удваивает учет", [receipt(), {"op": "post", "ref": "r", "status": 400, "expect": BASE}])
executable("LIFE-002", "lifecycle", "Отмена и повторное проведение продажи", [receipt(), issue(), {"op": "unpost", "ref": "s", "expect": BASE}, {"op": "post", "ref": "s", "expect": SOLD}])
executable("LIFE-003", "lifecycle", "Удаление черновика не меняет учет", [receipt(post=False), {"op": "delete", "ref": "r", "expect": EMPTY}])
executable("LIFE-004", "lifecycle", "Полный обратимый цикл покупки и продажи", [receipt(), issue(), {"op": "unpost", "ref": "s"}, {"op": "unpost", "ref": "r", "expect": EMPTY}, {"op": "post", "ref": "r"}, {"op": "post", "ref": "s", "expect": SOLD}])
executable("DIM-001", "master", "Изоляция двух организаций при одном контрагенте", [receipt(), goods("receipt", "b", 20, contract="BX1"), issue(), goods("issue", "bs", 6, 150, contract="BX1", expect=state({"AX1": [1200, 540], "BX1": [2400, 1080]}, {"A1": [7, 700], "B1": [14, 1400]}))])
executable("DIM-002", "master", "Изоляция двух договоров одного контрагента", [receipt(), goods("receipt", "r2", 20, contract="AX2"), issue(), goods("issue", "s2", 6, 150, contract="AX2", expect=state({"AX1": [1200, 540], "AX2": [2400, 1080]}, {"A1": [21, 2100]}))])
executable("DIM-003", "master", "Изоляция контрагентов одной организации", [receipt(), goods("receipt", "r2", 20, contract="AY1"), issue(), goods("issue", "s2", 6, 150, contract="AY1", expect=state({"AX1": [1200, 540], "AY1": [2400, 1080]}, {"A1": [21, 2100]}))])
executable("DIM-004", "master", "Договор чужой организации", [receipt(organization="B", warehouse="B1", post_status=400, expect=state({}, {}, movements={"r": {"inventory": 0, "settlements": 0}}))])
executable("DIM-005", "master", "Договор чужого контрагента", [receipt(counterparty="Y", post_status=400, expect=state({}, {}, movements={"r": {"inventory": 0, "settlements": 0}}))])
executable("PAY-007", "payments", "Аванс покупателя до отгрузки", [
    {"op": "payment", "ref": "p", "direction": "incoming", "amount": 500, "allow_advance": True, "date": "2026-10-01",
     "expect": state({}, {}, advances={"AX1": [0, 500]}, movements={"p": {"settlements": 1}})},
    goods("receipt", "r", 10, vat=0, contract="AX2"),
    goods("issue", "s", 6, 150, vat=0, expect=state({"AX1": [0, 400], "AX2": [1000, 0]}, {"A1": [4, 400]}, advances={},
        turnover={"from": "2026-10-02", "to": "2026-10-02", "contract": "AX1", "values": {
            "customer_advance_opening": 500, "customer_advance_closing": 0, "receivable_closing": 400}})),
    {"op": "unpost", "ref": "s", "expect": state({"AX2": [1000, 0]}, {"A1": [10, 1000]}, advances={"AX1": [0, 500]})},
    {"op": "post", "ref": "s", "expect": state({"AX1": [0, 400], "AX2": [1000, 0]}, {"A1": [4, 400]}, advances={})},
    {"op": "unpost", "ref": "p", "expect": state({"AX1": [0, 900], "AX2": [1000, 0]}, {"A1": [4, 400]}, advances={})},
])
executable("PAY-008", "payments", "Аванс поставщику", [
    {"op": "payment", "ref": "p", "direction": "outgoing", "amount": 400, "allow_advance": True,
     "expect": state({}, {}, advances={"AX1": [400, 0]})},
    goods("receipt", "r", 10, vat=0, expect=state({"AX1": [600, 0]}, {"A1": [10, 1000]}, advances={})),
    {"op": "unpost", "ref": "r", "expect": state({}, {}, advances={"AX1": [400, 0]})},
    {"op": "post", "ref": "r", "expect": state({"AX1": [600, 0]}, {"A1": [10, 1000]}, advances={})},
])
executable("PAY-009", "payments", "Переплата покупателя", [receipt(), issue(),
    {"op": "payment", "ref": "p", "direction": "incoming", "amount": 600, "allow_advance": True,
     "expect": state({"AX1": [1200, 0]}, {"A1": [7, 700]}, advances={"AX1": [0, 60]},
                     turnover={"from": "2026-10-01", "to": "2026-10-02", "contract": "AX1", "values": {
                         "customer_advance_closing": 60, "receivable_closing": 0, "receivable_payment_turnover": 600}})},
    {"op": "post", "ref": "p", "status": 400, "expect": {"advances": {"AX1": [0, 60]}}},
    {"op": "unpost", "ref": "p", "expect": {**SOLD, "advances": {}}},
])

# Each remaining contract includes a reproducible setup, business actions and
# explicit expected observables. They remain blocked until real adapters exist.
PENDING = {
"master": [
("DIM-006", "Упаковка и базовая единица", "Одна упаковка равна 12 штукам", "Принять 2 упаковки; продать 5 штук", {"stock_base_units": 19}),
("DIM-007", "Характеристики и серии", "Товар T, характеристики красный/синий, серии S1/S2", "Принять красный S1=5, синий S2=7; продать красный S1=2", {"red_S1": 3, "blue_S2": 7}),
("DIM-008", "Начальные остатки товаров и расчетов", "Пустая база; дата начала 01.10.2026", "Ввести 10 шт. стоимостью 1000, долг поставщику 1200 и покупателя 540; построить ОСВ за следующий день", {"opening_qty": 10, "opening_stock_cost": 1000, "opening_payable": 1200, "opening_receivable": 540})],
"procurement": [
("PUR-005", "Заказ поставщику и частичная приемка", "Заказ на 10 шт. по 100 без НДС", "Согласовать заказ; принять 4; затем 6", {"open_after_first": 6, "open_final": 0, "stock_final": 10, "payable_final": 1000}),
("PUR-006", "Отмена остатка заказа поставщику", "Заказ 10; принято 4", "Отменить оставшиеся 6", {"open_order": 0, "stock": 4, "payable": 400}),
("PUR-007", "Приемка до финансового документа", "Ордерный склад; поступление 10 шт. по 100 без НДС", "Провести приходный ордер; затем приобретение", {"physical_stock_after_order": 10, "payable_after_order": 0, "physical_stock_final": 10, "payable_final": 1000}),
("PUR-008", "Расхождения при приемке", "Поставщик отгрузил 10 по 100 без НДС; принято 8; согласована недопоставка", "Оформить акт расхождений и корректировку приобретения на 2", {"stock": 8, "payable": 800, "shortage": 2}),
("PUR-009", "Поступление услуг", "Услуга транспортировки 500 без НДС, не капитализируется", "Провести приобретение услуги", {"inventory_quantity_delta": 0, "payable": 500, "expense": 500}),
("PUR-010", "Закупка с авансом", "Перечислен аванс 400; поступление на 1000 без НДС", "Провести поступление; зачесть аванс", {"advance_remaining": 0, "payable": 600})],
"sales": [
("SAL-006", "Заказ клиента и частичные отгрузки", "Запас 10; заказ 6 по 150 без НДС", "Подтвердить заказ; отгрузить 2; затем 4", {"open_after_first": 4, "stock_final": 4, "receivable_final": 900}),
("SAL-007", "Отмена неотгруженного остатка", "Заказ 6; отгружено 2", "Отменить оставшиеся 4", {"open_order": 0, "released_reserve": 4, "receivable": 300}),
("SAL-008", "Ордерная отгрузка", "Запас 10; реализация 3 по 150 без НДС", "Оформить реализацию и расходный ордер в выбранной схеме однократного списания", {"stock_final": 7, "receivable": 450, "total_physical_expense": 3}),
("SAL-009", "Продажа услуги", "Услуга 500 без НДС", "Провести реализацию услуги", {"stock_quantity_delta": 0, "receivable": 500, "revenue": 500}),
("SAL-010", "Кредитный лимит клиента", "Лимит 1000; задолженность 900; новая продажа 200; строгий контроль включен", "Попытаться провести новую продажу", {"posting_rejected": True, "receivable": 900, "new_stock_expense": 0}),
("SAL-011", "Платежные этапы заказа", "Заказ 1000; аванс 30%, остаток после отгрузки", "Сформировать график; оплатить 300; отгрузить", {"advance_stage": 300, "final_stage": 700, "remaining_debt": 700})],
"availability": [
("AVL-001", "Резерв под заказ", "Запас 10; заказ клиента 6", "Зарезервировать заказ", {"physical_stock": 10, "reserved": 6, "available": 4, "receivable": 0}),
("AVL-002", "Частичная отгрузка резерва", "Запас 10; резерв 6", "Отгрузить по заказу 2", {"physical_stock": 8, "reserved": 4, "available": 4}),
("AVL-003", "Конкурирующие заказы", "Запас 10; строгий запрет сверхрезервирования", "Зарезервировать 6 под первый заказ; попытаться зарезервировать 6 под второй", {"first_reserved": 6, "second_reservation_rejected": True, "available": 4}),
("AVL-004", "Обеспечение закупкой", "Запас 0; заказ клиента 10; связанный заказ поставщику 10", "Принять 4 под назначение клиента", {"physical_stock": 4, "assigned_stock": 4, "uncovered_demand": 6}),
("AVL-005", "Снятие резерва при отмене", "Запас 10; резерв 6", "Отменить заказ клиента", {"reserved": 0, "available": 10}),
("AVL-006", "Обособленное обеспечение", "Запас под заказ A=5, под заказ B=4", "Попытаться списать 6 по заказу A без разрешения смены назначения", {"posting_rejected": True, "stock_A": 5, "stock_B": 4})],
"warehouse": [
("WH-004", "Инвентаризация: недостача", "Учетный запас 10 по 100; фактический 8", "Пересчитать; оформить списание недостачи 2", {"stock": 8, "stock_cost": 800, "shortage_expense": 200, "debt_delta": 0}),
("WH-005", "Инвентаризация: излишек", "Учетный запас 10 по 100; фактический 12; оценка излишка 100", "Пересчитать; оприходовать 2", {"stock": 12, "stock_cost": 1200, "surplus_income": 200}),
("WH-006", "Пересортица", "Товар T1=10 по 100; T2=0", "Переклассифицировать 2 единицы T1 в T2 без изменения стоимости", {"T1": 8, "T2": 2, "total_cost": 1000}),
("WH-007", "Адресное хранение", "Ячейки C1=10, C2=0 одного склада", "Переместить 4 в C2", {"C1": 6, "C2": 4, "warehouse_total": 10}),
("WH-008", "Товар в пути", "Двухэтапное перемещение 4 из A1 в A2; исходно A1=10", "Отправить 4; затем принять 4", {"in_transit_after_dispatch": 4, "in_transit_final": 0, "A1_final": 6, "A2_final": 4}),
("WH-009", "Порча товара", "Запас 10 по 100; испорчено 2", "Оформить порчу и списание", {"stock": 8, "expense": 200, "debt_delta": 0}),
("WH-010", "Запрет отрицательного остатка по серии", "Серия S1=2, S2=10", "Попытаться отгрузить 3 из S1", {"posting_rejected": True, "S1": 2, "S2": 10})],
"returns": [
("RET-001", "Частичный возврат клиента", "Принято 10 по 100; продано 3 по 150; без НДС и оплат", "Вернуть 1 из продажи", {"stock": 8, "stock_cost": 800, "receivable": 300, "net_revenue": 300, "net_cogs": 200}),
("RET-002", "Возврат оплаченной продажи", "Продано и оплачено 3 по 150 без НДС", "Вернуть 1; оформить возврат денег 150", {"refund_liability_before_payment": 150, "settlement_final": 0, "returned_qty": 1}),
("RET-003", "Возврат поставщику", "Принято 10 по 100 без НДС, не оплачено", "Вернуть 2 поставщику", {"stock": 8, "stock_cost": 800, "payable": 800}),
("RET-004", "Возврат оплаченной закупки", "Принято и оплачено 10 по 100 без НДС", "Вернуть 2; получить возврат денег 200", {"supplier_refund_due": 200, "settlement_final": 0, "stock": 8}),
("RET-005", "Возврат сверх исходной отгрузки", "Продано 3, уже возвращено 2", "Попытаться вернуть еще 2 по той же продаже", {"posting_rejected": True, "returned_total": 2}),
("RET-006", "Корректировка цены продажи", "Продано 3 по 150 без НДС", "Снизить цену до 140 корректировкой", {"quantity_delta": 0, "receivable": 420, "revenue_delta": -30}),
("RET-007", "Корректировка цены закупки", "Принято 10 по 100 без НДС; продаж нет", "Снизить цену закупки до 90 корректировкой", {"stock_qty": 10, "stock_cost": 900, "payable": 900}),
("RET-008", "Возврат после закрытия периода", "Продажа 3 по 150, закупочная 100; прошлый месяц закрыт", "В текущем месяце вернуть 1 по исходной продаже", {"current_qty_income": 1, "current_revenue_delta": -150, "current_cogs_delta": -100, "closed_period_changed": False})],
"payments": [
("PAY-010", "Разнесение оплаты по документам", "Один договор: долг по D1=300, D2=240; задан FIFO по сроку", "Получить 400", {"D1_balance": 0, "D2_balance": 140, "total_receivable": 140}),
("PAY-011", "Перенос задолженности между договорами", "AX1: долг клиента 540; AX2:0", "Перенести 200 с AX1 на AX2 без смены организации и контрагента", {"AX1_receivable": 340, "AX2_receivable": 200, "total_receivable": 540}),
("PAY-012", "Взаимозачет", "Один контрагент: нам должны 540, мы должны 1200", "Оформить взаимозачет на 540", {"receivable": 0, "payable": 660, "cash_delta": 0}),
("PAY-013", "Списание долга", "Долг покупателя 540; разрешено списание по основанию", "Списать 40 как расход", {"receivable": 500, "expense": 40, "cash_delta": 0}),
("PAY-014", "Просрочка по договорной дате", "Отгрузка 01.10 на 540; отсрочка 10 дней; оплат нет", "Построить просрочку на 05.10 и 12.10", {"overdue_oct05": 0, "overdue_oct12": 540, "days_overdue_oct12": 1})],
"treasury": [
("TRE-001", "Приход в кассу", "Касса=0; долг клиента 540", "Принять наличные 200 по ПКО", {"cash": 200, "receivable": 340}),
("TRE-002", "Расход из кассы", "Касса=1000; долг поставщику 1200", "Выплатить 500 по РКО", {"cash": 500, "payable": 700}),
("TRE-003", "Перевод банк-касса", "Банк=1000; касса=0; комиссия 0", "Перевести 300 из банка в кассу", {"bank": 700, "cash": 300, "total_cash": 1000, "debt_delta": 0}),
("TRE-004", "Эквайринг с комиссией", "Карточная продажа 1000; комиссия банка 2%", "Отразить оплату; получить отчет банка и зачисление", {"customer_debt": 0, "bank_receipt": 980, "bank_fee_expense": 20, "acquiring_balance": 0}),
("TRE-005", "Платежный календарь", "День 1: начальные деньги 100, поступление 200; день 2: выплата 400", "Построить календарь двух дней", {"day1_closing": 300, "day2_closing": -100, "day2_deficit": 100}),
("TRE-006", "Заявка на расходование денег", "Остаток банка 1000; заявка 500 требует согласования", "Создать заявку; согласовать; оплатить", {"bank_before_payment": 1000, "bank_final": 500, "paid_request": 500})],
"pricing": [
("PRC-001", "Цена по дате", "Цена T=150 до 10.10, затем 180; без НДС", "Продать 2 шт. 09.10 и 2 шт. 10.10", {"first_total": 300, "second_total": 360, "total_revenue": 660}),
("PRC-002", "Ручная скидка", "Цена 150; количество 3; скидка 10%; без НДС", "Продать со скидкой", {"gross_before_discount": 450, "discount": 45, "receivable": 405}),
("PRC-003", "Приоритет скидок", "База 1000; скидки 10% и 5%; политика: максимальная", "Применить обе акции", {"discount": 100, "sale_total": 900}),
("PRC-004", "Последовательные скидки", "База 1000; скидки 10% затем 5%; политика: последовательная", "Применить акции", {"discount": 145, "sale_total": 855}),
("PRC-005", "Соглашение и минимальная цена", "Минимальная цена 100; строгий контроль", "Попытаться продать по 90", {"posting_rejected": True, "revenue_delta": 0}),
("PRC-006", "Ретробонус", "Подходящая выручка 10000; бонус 3%; без НДС", "Начислить ретробонус клиенту", {"bonus": 300, "customer_benefit": 300})],
"cost": [
("COST-002", "Дополнительные расходы в стоимость", "Принято 10 по 100; капитализируемая доставка 200; без НДС", "Распределить доставку; продать 3", {"unit_cost": 120, "cogs": 360, "stock_cost": 840}),
("COST-003", "Валовая прибыль", "Закупка 10 по 100; продажа 3 по 150; без НДС", "Рассчитать себестоимость и прибыль", {"revenue": 450, "cogs": 300, "gross_profit": 150}),
("COST-004", "Закрытие месяца идемпотентно", "Выручка 450; себестоимость 300; иных расходов нет", "Закрыть месяц дважды", {"gross_profit_first": 150, "gross_profit_second": 150, "duplicate_cost_rows": 0}),
("COST-005", "Поздняя закупочная корректировка", "Принято 10 по 100; продано 3; без НДС; средняя", "Изменить закупочную цену до 110; пересчитать месяц", {"cogs": 330, "stock_cost": 770}),
("COST-006", "FIFO отдельно от средней", "Партии 10 по 100 и 10 по 200; политика FIFO", "Продать 12", {"cogs": 1400, "stock_qty": 8, "stock_cost": 1600}),
("COST-007", "Распределение по направлениям", "Общий расход 100; базы выручки направлений 300 и 700", "Распределить пропорционально выручке", {"direction_A_expense": 30, "direction_B_expense": 70, "allocated_total": 100})],
"vat_currency": [
("TAX-001", "НДС 20% сверх цены", "3 единицы по 150 без НДС; ставка 20%", "Провести реализацию и счет-фактуру", {"net": 450, "vat": 90, "gross": 540}),
("TAX-002", "НДС внутри цены", "Цена с НДС 180; 3 единицы; ставка 20%", "Провести реализацию", {"net": 450, "vat": 90, "gross": 540}),
("TAX-003", "Разные ставки в документе", "Строка1=100 без НДС ставка20%; строка2=100 ставка10%", "Провести реализацию", {"net": 200, "vat": 30, "gross": 230}),
("TAX-004", "НДС с аванса и зачет", "Аванс 1200 включает НДС20%; полная отгрузка 1200", "Выставить авансовый счет-фактуру; отгрузить; зачесть аванс", {"advance_vat": 200, "shipment_vat": 200, "advance_vat_reversal": 200, "net_vat": 200}),
("FX-001", "Валютная продажа", "100 USD; курс отгрузки 90; курс оплаты 92; без НДС", "Отгрузить и получить 100 USD", {"revenue_RUB": 9000, "receipt_RUB": 9200, "exchange_gain_RUB": 200, "debt_USD": 0}),
("FX-002", "Валютная закупка", "100 USD; курс приемки 90; курс оплаты 92; без НДС", "Принять и оплатить 100 USD", {"stock_RUB": 9000, "payment_RUB": 9200, "exchange_loss_RUB": 200, "debt_USD": 0}),
("IMP-001", "Импорт с пошлиной", "Стоимость 10000 RUB; пошлина10%; иных сборов нет; импортный НДС20%", "Оформить таможенную декларацию и капитализацию пошлины", {"duty": 1000, "vat_base": 11000, "import_vat": 2200, "stock_cost": 11000}),
("TAX-005", "Округление денежной строки", "Точность суммы2; округление half-up; 3 по 0.335 без НДС", "Рассчитать сумму строки", {"line_net": 1.01})],
"retail": [
("RTL-001", "Наличная розничная продажа", "Запас10 по100; чек2 по150 без НДС", "Пробить тестовый чек и закрыть смену в эмуляторе", {"stock": 8, "cash": 300, "revenue": 300, "cogs": 200}),
("RTL-002", "Розничный возврат", "Чек2 по150 без НДС; себестоимость100", "Вернуть1 по исходному чеку в эмуляторе", {"net_sold_qty": 1, "net_revenue": 150, "net_cogs": 100, "refund": 150}),
("RTL-003", "Смешанная оплата", "Чек1000; наличные400; карта600", "Провести чек в эмуляторе", {"cash": 400, "acquiring_claim": 600, "revenue": 1000}),
("RTL-004", "Бонусная программа", "Правило: начислять5% от оплаченной суммы1000", "Оплатить1000; начислить бонусы", {"earned_bonus_points": 50}),
("RTL-005", "Подарочный сертификат", "Продан сертификат1000; покупка600; без НДС в тестовом профиле", "Продать сертификат; частично погасить", {"certificate_remaining": 400, "goods_revenue": 600, "cash_received": 1000})],
"commission": [
("COM-001", "Передача комиссионеру", "Собственный запас10 по100", "Передать4 на комиссию без реализации", {"own_warehouse_qty": 6, "commission_qty": 4, "owned_total_cost": 1000, "revenue": 0}),
("COM-002", "Отчет комиссионера", "Передано4 по100; продано3 по150; вознаграждение10% от выручки; без НДС", "Провести отчет комиссионера", {"commission_stock": 1, "revenue": 450, "cogs": 300, "commission_fee": 45, "receivable_from_agent": 405}),
("COM-003", "Товар комитента", "Принято чужих10; учетная цена100", "Продать3 по150; вознаграждение10%; без НДС", {"third_party_stock": 7, "own_goods_cost": 0, "commission_revenue": 45, "payable_to_principal": 405}),
("COM-004", "Ответственное хранение", "Собственный запас10", "Передать хранителю4; вернуть1", {"own_warehouse_qty": 7, "custodian_qty": 3, "owned_total_qty": 10, "revenue": 0}),
("COM-005", "Возвратная тара", "Принято5 единиц тары; залог100 за единицу", "Вернуть3", {"container_qty": 2, "deposit_remaining": 200})],
"intercompany": [
("IC-001", "Продажа между организациями", "A:10 по100; B:0; передача4 по120 без НДС", "Оформить передачу A→B", {"A_qty": 6, "B_qty": 4, "A_cogs": 400, "A_receivable": 480, "B_payable": 480, "B_stock_cost": 480}),
("IC-002", "Возврат между организациями", "Передано A→B4 по120; исходная стоимостьA=100", "Вернуть1 от B к A по исходной передаче", {"A_qty": 7, "B_qty": 3, "intercompany_debt": 360}),
("IC-003", "Консолидированная прибыль", "A закупила4 по100 и передала B по120; B внешне продала2 по150; без НДС", "Исключить внутригрупповые обороты и нереализованную прибыль", {"external_revenue": 300, "group_cogs": 200, "group_profit": 100, "group_closing_cost": 200})],
"assembly": [
("ASM-001", "Сборка комплекта", "Компонент T1=4 по50; T2=2 по100; состав1комплект=2T1+1T2", "Собрать2 комплекта без дополнительных расходов", {"T1": 0, "T2": 0, "kits": 2, "kit_unit_cost": 200, "total_cost": 400}),
("ASM-002", "Разборка комплекта", "Комплект1 стоимость200; состав2T1+1T2; распределение стоимости100/100", "Разобрать комплект", {"kits": 0, "T1": 2, "T2": 1, "total_cost": 200}),
("ASM-003", "Недостаток компонента", "T1=1,T2=1; требуется2T1+1T2", "Попытаться собрать1 комплект", {"posting_rejected": True, "T1": 1, "T2": 1, "kits": 0}),
("ASM-004", "Внутреннее потребление", "Запас10 по100", "Передать в подразделение3 с признанием расхода", {"stock_qty": 7, "stock_cost": 700, "internal_expense": 300, "counterparty_debt_delta": 0})],
"planning": [
("PLN-001", "План-факт продаж", "План10 по150; факт6 по150; без НДС", "Сформировать отчет исполнения плана", {"plan_revenue": 1500, "actual_revenue": 900, "fulfillment_percent": 60, "quantity_gap": 4}),
("PLN-002", "Расчет потребности в закупке", "Потребность20; свободный запас5; ожидаемые поставки7", "Рассчитать закупочную потребность", {"purchase_requirement": 8}),
("PLN-003", "Минимальный и максимальный запас", "min10,max30; доступно8; правило пополнить до max", "Сформировать рекомендацию закупки", {"recommended_purchase_qty": 22})],
"reports": [
("REP-002", "Сверка складской оборотки", "Остаток10; приход5; расход3; перемещение2 между складами", "Построить оборотку и свод движений", {"group_closing_qty": 12, "opening_plus_in_minus_out": 12, "interwarehouse_net_qty": 0}),
("REP-003", "Сверка книги продаж с выручкой", "Две продажи нетто450 и200 со ставками20% и10%", "Сформировать книгу продаж и отчет выручки", {"net_revenue": 650, "output_vat": 110, "gross_sales": 760}),
("REP-004", "Акт сверки по договору", "Начальный долг300; начислено540; оплачено200", "Сформировать акт сверки за период", {"opening": 300, "accrual": 540, "payment": 200, "closing": 640}),
("REP-005", "Пустой период и несовместимые фильтры", "Данные только A/X/AX1; период без операций; нет входящих остатков", "Построить отчеты за пустой период и фильтр B/X/AX1", {"empty_period_turnover": 0, "incompatible_filter_rows": 0}),
("REP-006", "Раздельные направления без взаимозачета", "Один контрагент: кредиторская1200, дебиторская540", "Построить задолженность без документа взаимозачета", {"payable": 1200, "receivable": 540, "automatic_offset": 0})],
"lifecycle": [
("LIFE-005", "Запрет изменения проведенного документа", "Проведено поступление10 по100 без НДС", "Попытаться изменить цену на200 без отмены проведения", {"edit_rejected": True, "stock_cost": 1000, "payable": 1000}),
("LIFE-006", "Запрет отмены зависимого основания", "Поступление10; продажа8; отмена поступления создала бы минус8", "Попытаться отменить поступление", {"unpost_rejected": True, "stock": 2}),
("LIFE-007", "Закрытый период", "Период октябрь закрыт; документ датирован15.10", "Попытаться провести или изменить документ без специального разрешения", {"operation_rejected": True, "register_delta": 0}),
("LIFE-008", "Роли и организации доступа", "Пользователь имеет доступ только к A и чтению", "Попытаться провести документ A и прочитать документ B", {"write_forbidden": True, "foreign_organization_read_forbidden": True, "register_delta": 0}),
("LIFE-009", "Конкурентная продажа последнего остатка", "Запас1; два независимых клиента одновременно продают по1", "Провести оба документа конкурентно", {"successful_posts": 1, "failed_posts": 1, "stock": 0}),
("LIFE-010", "Транзакционная ошибка посреди проведения", "Запас10; продажа3; искусственная ошибка после складской записи", "Провести с fault injection; перечитать все регистры", {"document_posted": False, "stock": 10, "new_debt": 0, "partial_register_rows": 0}),
("LIFE-011", "Копирование документа", "Проведено поступление10 по100 без НДС", "Скопировать документ и оставить копию черновиком", {"distinct_uuid": True, "copy_posted": False, "stock": 10, "payable": 1000})],
"integration": [
("INT-001", "Повторная доставка документа обменом", "Один UUID поступления10 по100 без НДС; целевая тестовая база пуста", "Импортировать один пакет дважды", {"documents": 1, "stock": 10, "payable": 1000}),
("INT-002", "Отмена документа через обмен", "Импортировано проведенное поступление10 по100 без НДС; зависимостей нет", "Импортировать отмену проведения с тем же UUID", {"documents": 1, "posted": False, "stock": 0, "payable": 0}),
("INT-003", "Конфликт версий обмена", "Версия документа2 уже принята; пришла версия1", "Попытаться применить устаревший пакет", {"stored_version": 2, "stale_overwrite": False}),
("INT-004", "Маркировка: уникальность кода", "Тестовый контур ИСМП; один код маркировки уже принят", "Повторно принять тот же код с эмулятором ответа", {"accepted_unique_codes": 1, "duplicate_rejected": True}),
("INT-005", "ЭДО: повторный статус", "Один исходящий документ и UUID сообщения; тестовый транспорт", "Дважды доставить подтверждение подписи", {"business_documents": 1, "effective_confirmations": 1}),
("INT-006", "ЕГАИС: повторное подтверждение ТТН", "Тестовый транспорт; ТТН на10 единиц", "Повторно доставить подтверждение приемки", {"accepted_quantity": 10, "duplicate_stock_income": 0}),
("INT-007", "Прослеживаемость партии", "Партия РНПТ-A=10; другая РНПТ-B=5", "Отгрузить3 из РНПТ-A в тестовом контуре", {"RNPT_A": 7, "RNPT_B": 5, "tracked_shipped": 3})],
"crm": [
("CRM-001", "Коммерческое предложение в заказ", "Предложение3 по150 без НДС; запас10", "Согласовать предложение; создать заказ на основании", {"order_qty": 3, "order_amount": 450, "stock": 10, "receivable": 0}),
("CRM-002", "Выбор предложения поставщика", "Предложения на10: поставщикX по100, Y по110; правило минимальной цены", "Сравнить предложения; сформировать заказ победителю", {"selected_unit_price": 100, "order_amount": 1000, "new_payable": 0}),
("CRM-003", "Претензия без самопроизвольного списания", "Продажа3 по150; клиент оспаривает1; без НДС", "Зарегистрировать претензию без возврата и корректировки", {"receivable": 450, "stock_delta": 0, "revenue_delta": 0}),
("CRM-004", "Конверсия сделок", "4 сделки; 2 выиграны на300 и700, 1 проиграна, 1 открыта", "Построить воронку", {"won_count": 2, "won_amount": 1000, "win_rate_of_all_percent": 50})],
"logistics": [
("LOG-001", "Задание на доставку без повторной продажи", "Одна проведенная отгрузка3 по150 без НДС", "Создать задание на перевозку; подтвердить доставку", {"delivered_qty": 3, "total_revenue": 450, "additional_stock_expense": 0}),
("LOG-002", "Частичная доставка", "Отгружено6; доставлено4; 2 в пути", "Подтвердить частичную доставку; затем оставшиеся2", {"delivered_after_first": 4, "in_transit_after_first": 2, "delivered_final": 6}),
("LOG-003", "Заказ на перемещение", "A1=10; A2=0; заказ на4", "Создать заказ; переместить4 на основании", {"order_remaining": 0, "A1": 6, "A2": 4, "counterparty_debt_delta": 0}),
("LOG-004", "Расхождения после доставки", "Отправлено6, доставлено5; согласована недостача1 по100", "Оформить акт расхождений и основание ответственности", {"delivered_qty": 5, "shortage_qty": 1, "shortage_cost": 100})],
"marketplace": [
("MKT-001", "Повторный заказ маркетплейса", "Тестовый транспорт; внешний заказEXT1 на2 по150 без НДС", "Получить один заказ дважды", {"orders": 1, "ordered_qty": 2, "order_amount": 300}),
("MKT-002", "Отчет маркетплейса с удержанием", "Внешние продажи1000; комиссия100; логистика50; без НДС", "Импортировать отчет и выплату850 через тестовый транспорт", {"revenue": 1000, "selling_expenses": 150, "bank_receipt": 850, "agent_debt": 0}),
("MKT-003", "Отмена до отгрузки", "Заказ2; резерв2; отгрузки нет", "Получить отмену из тестового транспорта", {"reserved": 0, "revenue": 0, "receivable": 0}),
("MKT-004", "Заказ торгового представителя офлайн", "Один внешний UUID заказа3 по150 без НДС", "Синхронизировать заказ дважды после восстановления связи", {"orders": 1, "ordered_qty": 3, "order_amount": 450})],
}


# Stage two: linked returns and refunds, with cancellation and reposting.
def ret(ref, source, quantity, **kw):
    return {"op": "return", "ref": ref, "source": source, "quantity": quantity, **kw}


def refund(ref, source, amount, **kw):
    return {"op": "refund", "ref": ref, "source": source, "amount": amount, **kw}


executable("RET-001", "returns", "Частичный возврат клиента", [receipt(vat=0), issue(vat=0),
    ret("ret", "s", 1, expect=state({"AX1": [1000, 300]}, {"A1": [8, 800]}, movements={"ret": {"inventory": 1, "settlements": 1}}, financials={"net_revenue": 300, "net_cogs": 200})),
    {"op": "unpost", "ref": "s", "status": 400},
    {"op": "unpost", "ref": "ret", "expect": state({"AX1": [1000, 450]}, {"A1": [7, 700]})},
    {"op": "post", "ref": "ret", "expect": state({"AX1": [1000, 300]}, {"A1": [8, 800]})}])
executable("RET-002", "returns", "Возврат оплаченной продажи", [receipt(vat=0), issue(vat=0),
    {"op": "payment", "ref": "p", "direction": "incoming", "amount": 450},
    ret("ret", "s", 1, expect=state({"AX1": [1000, 0]}, {"A1": [8, 800]}, advances={"AX1": [0, 150]})),
    refund("f", "ret", 150, expect={"advances": {}, "debts": {"AX1": [1000, 0]}, "movements": {"f": {"cash": 1, "settlements": 1}}}),
    {"op": "unpost", "ref": "ret", "status": 400}, {"op": "post", "ref": "f", "status": 400},
    {"op": "unpost", "ref": "f", "expect": {"advances": {"AX1": [0, 150]}}},
    {"op": "post", "ref": "f", "expect": {"advances": {}}}])
executable("RET-003", "returns", "Возврат поставщику", [receipt(vat=0),
    ret("ret", "r", 2, expect=state({"AX1": [800, 0]}, {"A1": [8, 800]})),
    {"op": "unpost", "ref": "r", "status": 400},
    {"op": "unpost", "ref": "ret", "expect": state({"AX1": [1000, 0]}, {"A1": [10, 1000]})},
    {"op": "post", "ref": "ret", "expect": state({"AX1": [800, 0]}, {"A1": [8, 800]})}])
executable("RET-004", "returns", "Возврат оплаченной закупки", [receipt(vat=0),
    {"op": "payment", "ref": "p", "direction": "outgoing", "amount": 1000},
    ret("ret", "r", 2, expect={"advances": {"AX1": [200, 0]}}),
    refund("f", "ret", 200, expect=state({}, {"A1": [8, 800]}, advances={}, movements={"f": {"cash": 1, "settlements": 1}})),
    {"op": "unpost", "ref": "f", "expect": {"advances": {"AX1": [200, 0]}}},
    {"op": "post", "ref": "f", "expect": {"advances": {}}}])
executable("RET-005", "returns", "Возврат сверх исходной отгрузки", [receipt(vat=0), issue(vat=0),
    ret("ret", "s", 2), ret("draft", "s", 1, post=False), ret("last", "s", 1),
    {"op": "post", "ref": "draft", "status": 400, "expect": state({"AX1": [1000, 0]}, {"A1": [10, 1000]}, movements={"draft": {"inventory": 0, "settlements": 0}})},
    {"op": "unpost", "ref": "last"},
    ret("excess", "s", 2, create_status=400, expect=state({"AX1": [1000, 150]}, {"A1": [9, 900]})),
    {"op": "unpost", "ref": "ret"}, {"op": "post", "ref": "draft", "expect": state({"AX1": [1000, 300]}, {"A1": [8, 800]})}])
executable("RET-006", "returns", "Корректировка цены продажи", [receipt(vat=0), issue(vat=0),
    {"op": "adjustment", "ref": "adj", "source": "s", "price": 140,
     "expect": state({"AX1": [1000, 420]}, {"A1": [7, 700]}, financials={"net_revenue": 420, "net_cogs": 300, "revenue_delta": -30}, movements={"adj": {"inventory": 0, "settlements": 1}})},
    {"op": "post", "ref": "adj", "status": 400}, {"op": "unpost", "ref": "s", "status": 400},
    {"op": "unpost", "ref": "adj", "expect": state({"AX1": [1000, 450]}, {"A1": [7, 700]})},
    {"op": "post", "ref": "adj", "expect": state({"AX1": [1000, 420]}, {"A1": [7, 700]}, financials={"revenue_delta": -30})}])
executable("RET-007", "returns", "Корректировка цены закупки", [receipt(vat=0),
    {"op": "adjustment", "ref": "adj", "source": "r", "price": 90,
     "expect": state({"AX1": [900, 0]}, {"A1": [10, 900]}, movements={"adj": {"inventory": 1, "settlements": 1}})},
    {"op": "post", "ref": "adj", "status": 400}, {"op": "unpost", "ref": "r", "status": 400},
    {"op": "unpost", "ref": "adj", "expect": state({"AX1": [1000, 0]}, {"A1": [10, 1000]})},
    {"op": "post", "ref": "adj", "expect": state({"AX1": [900, 0]}, {"A1": [10, 900]})}])
PENDING["returns"] = [case for case in PENDING["returns"] if case[0] not in {f"RET-{n:03d}" for n in range(1, 8)}]

# STEP-02: explicit references and a dedicated opening-balance recorder.
executable('DIM-006', 'master', 'Упаковка и базовая единица', [
    {'op': 'reference', 'ref': 'box12', 'kind': 'material-packages', 'name': 'Упаковка 12 шт.', 'factor': 12},
    goods('receipt', 'r', 2, 1200, vat=0, date='2026-10-01', package='box12'),
    goods('issue', 's', 5, 150, vat=0, expect=state({'AX1': [2400, 750]}, {'A1': [19, 1900]}, dimensions={'stock_base_units': 19})),
    {'op': 'unpost', 'ref': 's', 'expect': {'stock': {'A1': [24, 2400]}}},
    {'op': 'post', 'ref': 's', 'expect': {'dimensions': {'stock_base_units': 19}}},
])
executable('DIM-007', 'master', 'Характеристики и серии', [
    {'op': 'reference', 'ref': 'red', 'kind': 'material-characteristics', 'name': 'Красный'},
    {'op': 'reference', 'ref': 'blue', 'kind': 'material-characteristics', 'name': 'Синий'},
    {'op': 'reference', 'ref': 'S1', 'kind': 'material-series', 'name': 'S1', 'characteristic': 'red'},
    {'op': 'reference', 'ref': 'S2', 'kind': 'material-series', 'name': 'S2', 'characteristic': 'blue'},
    goods('receipt', 'r', 5, 100, vat=0, date='2026-10-01', characteristic='red', series='S1'),
    goods('receipt', 'b', 7, 300, vat=0, date='2026-10-01', characteristic='blue', series='S2'),
    goods('issue', 's', 2, 150, vat=0, characteristic='red', series='S1',
          expect={'dimensions': {'red_S1': 3, 'blue_S2': 7}, 'financials': {'net_revenue': 300, 'net_cogs': 200}}),
    {'op': 'unpost', 'ref': 's', 'expect': {'dimensions': {'red_S1': 5, 'blue_S2': 7}}},
    {'op': 'post', 'ref': 's', 'expect': {'dimensions': {'red_S1': 3, 'blue_S2': 7}}},
])
executable('DIM-008', 'master', 'Начальные остатки товаров и расчетов', [
    {'op': 'opening', 'ref': 'open', 'date': '2026-10-01', 'quantity': 10, 'cost': 1000, 'payable': 1200, 'receivable': 540,
     'expect': state({'AX1': [1200, 540]}, {'A1': [10, 1000]},
        dimensions={'opening_qty': 10, 'opening_stock_cost': 1000, 'opening_payable': 1200, 'opening_receivable': 540},
        financials={'net_revenue': 0, 'net_cogs': 0}, movements={'open': {'inventory': 1, 'settlements': 2}})},
    {'op': 'post', 'ref': 'open', 'status': 400},
    {'op': 'unpost', 'ref': 'open', 'expect': EMPTY},
    {'op': 'post', 'ref': 'open', 'expect': {'dimensions': {'opening_qty': 10, 'opening_stock_cost': 1000, 'opening_payable': 1200, 'opening_receivable': 540}}},
])
PENDING['master'] = [case for case in PENDING['master'] if case[0] not in {'DIM-006', 'DIM-007', 'DIM-008'}]


def build():
    for area, contracts in PENDING.items():
        for ident, title, setup, actions, expected in contracts:
            add(ident, area, title,
                [{"op": "business_contract", "action": action.strip()} for action in actions.split(";")]
                + [{"op": "observe", "expect": expected}], preconditions=[setup],
                adapter='api-v1' if ident in {'LIFE-005', 'LIFE-006', 'LIFE-008', 'LIFE-009', 'LIFE-010', 'LIFE-011', 'PUR-005', 'PUR-006', 'PUR-007', 'PUR-008', 'PUR-009', 'PUR-010','SAL-006','SAL-007','SAL-008','SAL-009','SAL-010'} else None,
                profile="integration-sandbox" if area == "integration" else "extended" if area in (
                    "retail", "commission", "intercompany", "assembly", "planning", "vat_currency") else "core")
    target = HERE / "scenarios"
    target.mkdir(exist_ok=True)
    catalog = {"schema_version": 1, "reference_version": "11.5.20.80",
               "fixture": "trade-v1", "areas": {key: {"title": val[0], "ut_subsystem": val[1]} for key, val in AREAS.items()},
               "scenarios": SCENARIOS}
    (target / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixture = {"id": "trade-v1", "organizations": ["A", "B"], "counterparties": ["X", "Y"],
               "contracts": {"AX1": ["A", "X"], "AX2": ["A", "X"], "AY1": ["A", "Y"], "BX1": ["B", "X"]},
               "warehouses": {"A1": "A", "A2": "A", "B1": "B"}, "currency": "RUB",
               "vat_rate": 20, "payment_deferral_days": 10, "cost_policy": "weighted_average",
               "isolation": "fresh_database_per_scenario", "external_transports": "emulators_only"}
    (target / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Сценарии торгового учета УТ11 / CTM", "",
             "Эталон структуры: УТ 11.5.20.80. Авторские бизнес-контракты; числовые ожидания",
             "не объявляются результатами выполнения в 1С. Полный сценарный адаптер УТ пока отсутствует.", "",
             f"Всего {len(SCENARIOS)} сценариев в {len(AREAS)} разделах; исполняемых в CTM — {sum(s['execution']['ctm'] is not None for s in SCENARIOS)}.", "",
             "Порядок запуска и границы проверки: [TRADE_ACCOUNTING_SUITE.md](TRADE_ACCOUNTING_SUITE.md).", "",
             "| Раздел | Сценариев | Исполняемых CTM |", "|---|---:|---:|"]
    for area, details in AREAS.items():
        cases = [s for s in SCENARIOS if s["area"] == area]
        lines.append(f"| {details[0]} | {len(cases)} | {sum(s['execution']['ctm'] is not None for s in cases)} |")
    for area, details in AREAS.items():
        lines.extend(["", f"## {details[0]}", "", f"Подсистема УТ: `{details[1]}`."])
        for case in (s for s in SCENARIOS if s["area"] == area):
            lines.extend(["", f"### {case['id']} — {case['title']}", "",
                          f"Приоритет: {case['priority']}; профиль: `{case['profile']}`; CTM: "
                          + ("есть API-адаптер" if case["execution"]["ctm"] else "заблокирован: нет сценарного адаптера") + ".", "",
                          "Условия: " + "; ".join(case["preconditions"]) + ".", "",
                          "Объекты УТ: " + ", ".join(f"`{obj}`" for obj in case["ut_objects"]) + ".", "",
                          "Шаги и ожидаемые наблюдения:", "", "```json",
                          json.dumps(case["steps"], ensure_ascii=False, indent=2), "```"])
    (HERE.parents[1] / "TRADE_ACCOUNTING_SCENARIOS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Authored {len(SCENARIOS)} scenarios; executable CTM: {sum(s['execution']['ctm'] is not None for s in SCENARIOS)}")


if __name__ == "__main__":
    build()
