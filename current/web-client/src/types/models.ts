export type ReferenceKind =
  | 'counterparties'
  | 'objects'
  | 'works'
  | 'persons'
  | 'organizations'
  | 'contracts'
  | 'materials'

export interface UserInfo {
  id: number
  username: string
  role: string
  is_active: boolean
  person_id?: number | null
  full_name?: string | null
  use_specification_review?: boolean
}

export interface Counterparty {
  id: number
  name: string
  display_name?: string
  inn?: string | null
  contact_person?: string | null
  phone?: string | null
  parent_id?: number | null
  marked_for_deletion: boolean
  is_group: boolean
}

export interface ObjectRecord {
  id: number
  name: string
  display_name?: string
  address?: string | null
  owner_id?: number | null
  owner_name?: string | null
  parent_id?: number | null
  marked_for_deletion: boolean
  is_group: boolean
}

export interface WorkRecord {
  id: number
  name: string
  display_name?: string
  code?: string | null
  unit?: string | null
  price: number
  labor_rate: number
  specification_review_status?: 'ok' | 'incorrect' | 'corrected'
  specification_review_note?: string | null
  parent_id?: number | null
  marked_for_deletion: boolean
  is_group: boolean
}

export type ComponentType = 'Material' | 'Labor' | 'Equipment' | 'Other'

export interface UnitRecord {
  id: number
  name: string
  short_name?: string | null
}

export interface MaterialRecord {
  id: number
  code?: string | null
  name: string
  unit_id?: number | null
  unit_name?: string | null
  price: number
}

export interface WorkSpecificationRecord {
  id?: number
  work_id?: number
  component_type: ComponentType
  component_name: string
  unit_id?: number | null
  unit_name?: string | null
  consumption_rate: number
  unit_price: number
  total_cost: number
  material_id?: number | null
  modified_at?: string | null
}

export interface WorkDetail extends WorkRecord {
  specifications: WorkSpecificationRecord[]
}

export interface ImportedSpecificationRow {
  source_row: number
  component_type?: string | null
  component_name?: string | null
  material_code?: string | null
  material_id?: number | null
  material_status?: 'existing' | 'new' | null
  matched_material_name?: string | null
  matched_material_code?: string | null
  unit_name?: string | null
  unit_id?: number | null
  unit_status?: 'existing' | 'new' | null
  consumption_rate?: number | null
  unit_price?: number | null
  total_cost: number
  errors: string[]
  warnings?: string[]
}

export interface MissingImportedMaterial {
  material_name: string
  material_code?: string | null
  unit_name?: string | null
  unit_id?: number | null
  unit_status?: 'existing' | 'new' | null
  unit_price: number
  source_row_numbers: number[]
}

export interface ImportMaterialCreateResult {
  material_id: number
  material_name: string
  material_code?: string | null
  unit_id?: number | null
  unit_name?: string | null
  price: number
  status: 'created' | 'reused'
  source_row_numbers: number[]
}

export interface WorkCorrectionImportWorkResult {
  work_id: number
  work_uuid?: string | null
  work_code?: string | null
  work_name: string
  row_count: number
  specification_count: number
  specification_review_status: 'ok' | 'incorrect' | 'corrected'
}

export interface WorkCorrectionImportResult {
  updated_work_count: number
  updated_specification_count: number
  works: WorkCorrectionImportWorkResult[]
}

export interface ImportPreview {
  rows: ImportedSpecificationRow[]
  valid_count: number
  error_count: number
  missing_materials: MissingImportedMaterial[]
}

export interface PersonRecord {
  id: number
  full_name: string
  display_name?: string
  personnel_number?: string | null
  position?: string | null
  phone?: string | null
  hourly_rate?: number
  user_id?: number | null
  username?: string | null
  parent_id?: number | null
  marked_for_deletion: boolean
  is_group: boolean
}

export interface OrganizationRecord {
  id: number
  name: string
  display_name?: string
  inn?: string | null
  default_responsible_id?: number | null
  default_responsible_name?: string | null
  parent_id?: number | null
  marked_for_deletion: boolean
  is_group: boolean
}

export interface ContractRecord {
  id: number
  number: string
  display_name?: string
  date?: string | null
  organization_id?: number | null
  organization_name?: string | null
  counterparty_id?: number | null
  counterparty_name?: string | null
  parent_id?: number | null
  parent_number?: string | null
  amount: number
  kind?: string
  currency?: string
  vat_rate?: number
  payment_deferral_days?: number
  agreement_date?: string | null
  valid_until?: string | null
  description?: string | null
  marked_for_deletion: boolean
  is_group: boolean
}

export type ReferenceRecord =
  | Counterparty
  | ObjectRecord
  | WorkRecord
  | PersonRecord
  | OrganizationRecord
  | ContractRecord

export interface EstimateLine {
  id?: number
  estimate_id?: number
  line_number: number
  work_id?: number | null
  work_name?: string | null
  quantity: number
  unit?: string | null
  price: number
  labor_rate: number
  sum: number
  planned_labor: number
  is_group: boolean
  group_name?: string | null
  parent_group_id?: number | null
  is_collapsed: boolean
}

export interface Estimate {
  id?: number
  number: string
  date: string
  customer_id?: number | null
  object_id?: number | null
  contractor_id?: number | null
  responsible_id?: number | null
  contract_id?: number | null
  contract_number?: string | null
  total_sum: number
  total_labor: number
  is_posted: boolean
  posted_at?: string | null
  marked_for_deletion?: boolean
  customer_name?: string | null
  object_name?: string | null
  contractor_name?: string | null
  responsible_name?: string | null
  lines: EstimateLine[]
}

export interface DailyReportLine {
  id?: number
  report_id?: number
  line_number: number
  work_id?: number | null
  work_name?: string | null
  planned_labor: number
  actual_labor: number
  deviation_percent: number
  quantity: number
  unit?: string | null
  price: number
  actual_sum: number
  executor_ids: number[]
  executor_names?: string[]
  is_group: boolean
  group_name?: string | null
  parent_group_id?: number | null
  is_collapsed: boolean
}

export interface DailyReport {
  id?: number
  number: string
  date: string
  estimate_id?: number | null
  estimate_number?: string | null
  foreman_id?: number | null
  foreman_name?: string | null
  supplementary_agreement_id?: number | null
  supplementary_agreement_number?: string | null
  is_posted: boolean
  posted_at?: string | null
  marked_for_deletion?: boolean
  based_on_type?: string | null
  based_on_id?: number | null
  based_on_number?: string | null
  lines: DailyReportLine[]
}

export interface TimesheetLine {
  id?: number
  timesheet_id?: number
  line_number: number
  employee_id: number
  employee_name?: string | null
  hourly_rate: number
  days: Record<number, number>
  total_hours: number
  total_amount: number
}

export interface Timesheet {
  id?: number
  number: string
  date: string
  object_id?: number | null
  object_name?: string | null
  estimate_id?: number | null
  estimate_number?: string | null
  foreman_id?: number | null
  foreman_name?: string | null
  month_year: string
  is_posted: boolean
  posted_at?: string | null
  marked_for_deletion?: boolean
  total_hours: number
  total_amount: number
  based_on_type?: string | null
  based_on_id?: number | null
  based_on_number?: string | null
  lines: TimesheetLine[]
}

export interface TimesheetImportPreview {
  document_info: {
    type?: string
    version?: string
    number?: string
    date?: string
    month_year?: string
    is_posted?: boolean
    object_name?: string
    estimate_number?: string
    foreman_name?: string
  }
  lines: TimesheetLine[]
  imported_rows: {
    source_line_number: number
    employee_name: string
    personnel_number?: string | null
    position?: string | null
    hourly_rate?: number | null
    days: Record<number, number>
    total_hours: number
    total_amount: number
    matched_employee_id?: number | null
    matched_employee_name?: string | null
    matched_by?: 'full_name' | 'personnel_number' | null
  }[]
  missing_employees: {
    employee_name: string
    hourly_rate: number
    source_line_numbers: number[]
  }[]
  requires_employee_creation: boolean
}

export interface WorkExecutionItem {
  id?: number
  recorder_type: string
  recorder_id: number
  recorder_number?: string | null
  line_number: number
  period: string
  object_id?: number | null
  object_name?: string | null
  estimate_id?: number | null
  estimate_number?: string | null
  work_id?: number | null
  work_name?: string | null
  customer_id?: number | null
  customer_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  quantity_income: number
  quantity_expense: number
  sum_income: number
  sum_expense: number
  balance_quantity: number
  balance_sum: number
}

export interface WorkExecutionResponse {
  items: WorkExecutionItem[]
  totals: {
    quantity_income: number
    quantity_expense: number
    sum_income: number
    sum_expense: number
    balance_quantity: number
    balance_sum: number
  }
}

export interface DashboardSummary {
  documents: {
    estimates: number
    daily_reports: number
    timesheets: number
  }
  references: Record<string, number>
  register_totals: {
    quantity_income: number
    quantity_expense: number
    sum_income: number
    sum_expense: number
  }
}

// --- Sync ---

export type SyncOperation = 'INSERT' | 'UPDATE' | 'DELETE'

export interface SyncNodeInfo {
  id: string
  code: string
  name: string
  is_local: boolean
  last_sync_in?: string | null
  last_sync_out?: string | null
  sent_packet_no: number
  received_packet_no: number
}

export interface SyncChangeEnvelope {
  change_id?: number | null
  entity_type: string
  entity_uuid: string
  operation: SyncOperation
  created_at?: string | null
  updated_at?: string | null
  payload?: Record<string, unknown> | null
}

export interface SyncConflictRecord {
  id?: string
  entity_type: string
  entity_uuid: string
  resolution?: string
  conflict_resolution?: string
  local_updated_at?: string | null
  remote_updated_at?: string | null
  arrival_time?: string | null
  resolved_at?: string | null
  payload?: Record<string, unknown> | null
}

export interface SyncRegisterResponse {
  node: SyncNodeInfo
  local_node: SyncNodeInfo
  schema_version: string
}

export interface SyncExchangeRequest {
  schema_version: string
  node_id?: string | null
  node_code: string
  node_name: string
  last_received_change_id: number
  batch_size: number
  changes: SyncChangeEnvelope[]
}

export interface SyncExchangeResponse {
  schema_version: string
  local_node: SyncNodeInfo
  remote_node: SyncNodeInfo
  processed_count: number
  skipped_count: number
  error_count: number
  outgoing_count: number
  last_sent_change_id: number
  changes: SyncChangeEnvelope[]
  conflicts: SyncConflictRecord[]
  errors: string[]
}

export interface SyncStatusResponse {
  schema_version: string
  local_node: SyncNodeInfo
  nodes: SyncNodeInfo[]
  pending_changes: number
}

// --- Payments ---

export type PaymentDirection = 'incoming' | 'outgoing'
export type PaymentCategory = 'customer_stage' | 'payroll' | 'supplier' | 'tax' | 'supplier_invoice' | 'customer_invoice' | 'other'
export type PaymentSourceKind = 'manual' | 'work_execution' | 'payroll' | 'goods_receipt' | 'goods_issue'

export interface PaymentScheduleLine {
  id?: number
  line_number: number
  direction: PaymentDirection
  category: PaymentCategory
  planned_date: string
  counterparty_id?: number | null
  contract_id?: number | null
  estimate_id?: number | null
  object_id?: number | null
  planned_amount: number
  description?: string | null
  source_kind?: PaymentSourceKind
  source_ref?: string | null
  is_group?: boolean
  group_name?: string | null
  parent_group_id?: number | null
  parent_group_uuid?: string | null
  is_collapsed?: boolean
  uuid?: string | null
  counterparty_name?: string | null
  contract_number?: string | null
  estimate_number?: string | null
  object_name?: string | null
  fact_amount?: number
  balance?: number
}

export interface PaymentSchedule {
  id: number
  uuid?: string | null
  number: string
  date_from: string
  date_to: string
  object_id?: number | null
  contract_id?: number | null
  responsible_id?: number | null
  is_posted: boolean
  posted_at?: string | null
  marked_for_deletion: boolean
  created_at?: string | null
  modified_at?: string | null
  updated_at?: string | null
  object_name?: string | null
  contract_number?: string | null
  responsible_name?: string | null
  based_on_type?: string | null
  based_on_id?: number | null
  based_on_number?: string | null
  total_incoming: number
  total_outgoing: number
  lines: PaymentScheduleLine[]
}

export interface PaymentTransaction {
  id: number
  uuid?: string | null
  number: string
  date: string
  direction: PaymentDirection
  category: PaymentCategory
  counterparty_id?: number | null
  contract_id?: number | null
  estimate_id?: number | null
  object_id?: number | null
  linked_schedule_id?: number | null
  linked_line_id?: number | null
  amount: number
  description?: string | null
  is_posted: boolean
  posted_at?: string | null
  marked_for_deletion: boolean
  created_at?: string | null
  modified_at?: string | null
  updated_at?: string | null
  counterparty_name?: string | null
  contract_number?: string | null
  linked_line_uuid?: string | null
  based_on_type?: string | null
  based_on_id?: number | null
  based_on_number?: string | null
}

export interface PaymentRegisterItem {
  planned_date?: string | null
  direction: PaymentDirection
  category: PaymentCategory
  counterparty_id?: number | null
  counterparty_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  object_id?: number | null
  object_name?: string | null
  estimate_id?: number | null
  estimate_number?: string | null
  planned_amount: number
  fact_amount: number
  balance: number
  is_overdue: boolean
  is_paid: boolean
}

export interface PaymentRegisterTotals {
  incoming_planned: number
  outgoing_planned: number
  incoming_fact: number
  outgoing_fact: number
  net_flow: number
}

export interface PaymentRegisterResponse {
  items: PaymentRegisterItem[]
  totals: PaymentRegisterTotals
}

export interface CashflowDayItem {
  date: string
  incoming_planned: number
  outgoing_planned: number
  incoming_fact: number
  outgoing_fact: number
  cumulative_balance: number
  is_deficit: boolean
}

// --- Goods (ТМЦ) ---

export type GoodsKind = 'receipt' | 'issue'

export interface GoodsLine {
  id?: number
  uuid?: string | null
  line_number: number
  material_id?: number | null
  material_code?: string | null
  name: string
  unit_id?: number | null
  unit?: string | null
  unit_name?: string | null
  quantity: number
  price_without_vat: number
  vat_rate: number
  vat_amount: number
  sum_without_vat: number
  sum_with_vat: number
  object_id?: number | null
  object_name?: string | null
  drawing_code?: string | null
  note?: string | null
}

export interface GoodsDocument {
  id: number
  uuid?: string | null
  kind: GoodsKind
  number: string
  date: string
  organization_id: number
  organization_name?: string | null
  counterparty_id?: number | null
  counterparty_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  object_id?: number | null
  object_name?: string | null
  estimate_id?: number | null
  responsible_id?: number | null
  responsible_name?: string | null
  sum_without_vat: number
  vat_amount: number
  sum_with_vat: number
  due_date?: string | null
  description?: string | null
  is_posted: boolean
  posted_at?: string | null
  marked_for_deletion: boolean
  based_on_type?: string | null
  based_on_id?: number | null
  based_on_number?: string | null
  created_at?: string | null
  modified_at?: string | null
  updated_at?: string | null
  lines: GoodsLine[]
}

/** A line submitted to the API (totals are computed server-side). */
export interface GoodsLineInput {
  id?: number
  line_number: number
  material_id?: number | null
  name: string
  unit_id?: number | null
  unit?: string | null
  quantity: number
  price_without_vat: number
  vat_rate: number
  object_id?: number | null
  drawing_code?: string | null
  note?: string | null
  uuid?: string | null
}

export type GoodsDocumentPayload = Omit<GoodsDocument, 'id' | 'kind' | 'sum_without_vat' | 'vat_amount' | 'sum_with_vat' | 'is_posted' | 'posted_at' | 'marked_for_deletion' | 'created_at' | 'modified_at' | 'updated_at' | 'organization_name' | 'counterparty_name' | 'contract_number' | 'object_name' | 'responsible_name' | 'lines'> & {
  id?: number
  auto_schedule?: boolean
  lines: GoodsLineInput[]
}

// --- Inventory register ---

export interface InventoryBalanceItem {
  material_id?: number | null
  material_code?: string | null
  material_name?: string | null
  object_id?: number | null
  object_name?: string | null
  unit_id?: number | null
  unit_name?: string | null
  quantity_income: number
  quantity_expense: number
  quantity_balance: number
  sum_income: number
  sum_expense: number
  average_price: number
}

export interface InventoryMovementItem {
  period: string
  recorder_type: string
  recorder_id: number
  line_number: number
  material_id?: number | null
  material_code?: string | null
  material_name?: string | null
  object_id?: number | null
  object_name?: string | null
  unit_id?: number | null
  unit_name?: string | null
  quantity_income: number
  quantity_expense: number
  sum_income: number
  sum_expense: number
}

// --- Mutual settlements ---

export type SettlementDirection = 'receivable' | 'payable'

export interface SettlementBalanceItem {
  organization_id: number
  organization_name?: string | null
  counterparty_id?: number | null
  counterparty_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  object_id?: number | null
  object_name?: string | null
  receivable_accrual: number
  receivable_payment: number
  receivable_balance: number
  payable_accrual: number
  payable_payment: number
  payable_balance: number
}

export interface SettlementTurnoverRow {
  organization_id: number
  organization_name?: string | null
  counterparty_id?: number | null
  counterparty_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  // receivable = Дт (нам должны); payable = Кт (мы должны)
  receivable_opening: number
  receivable_accrual_turnover: number
  receivable_payment_turnover: number
  receivable_closing: number
  payable_opening: number
  payable_accrual_turnover: number
  payable_payment_turnover: number
  payable_closing: number
  period_from: string
  period_to: string
}

export interface SettlementLedgerItem {
  period: string
  recorder_type: string
  recorder_id: number
  line_number: number
  direction: SettlementDirection
  accrual_amount: number
  payment_amount: number
  planned_amount: number
  contract_id?: number | null
  contract_number?: string | null
  object_id?: number | null
  object_name?: string | null
  receivable_balance_running: number
  payable_balance_running: number
}

export interface OverdueItem {
  organization_id: number
  organization_name?: string | null
  counterparty_id?: number | null
  counterparty_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  direction: SettlementDirection
  overdue_amount: number
  period?: string | null
  days_overdue: number
}

// --- Excel import profiles ---

export type ImportProfileTarget = 'goods_receipt' | 'goods_issue' | 'work_specification'

export type SkipMatchMode = 'empty' | 'non_empty' | 'non_number' | 'equals' | 'contains' | 'regex' | 'starts_with' | 'ends_with'

export interface ColumnSkipRule {
  column_index: number // 1-based
  match_mode: SkipMatchMode
  pattern?: string | null
}

export interface ImportProfile {
  name: string
  target: ImportProfileTarget
  sheet?: string | number | null
  header_row?: number
  data_start_row?: number | null
  data_end_row?: number | null
  column_mapping?: Record<string, number>
  overrides?: Record<string, string | number | boolean | null>
  price_multiplier_column?: number | null
  sum_column?: number | null
  sum_with_vat_column?: number | null
  skip_rules?: ColumnSkipRule[]
  material_resolve_by?: 'none' | 'code' | 'name' | 'code_or_name'
  create_missing_materials?: boolean
  create_missing_units?: boolean
  stop_on_first_empty_name?: boolean
  description?: string
}

export interface GoodsImportPreview {
  filename: string
  detected_columns?: Record<string, number>
  rows: GoodsLine[]
  warnings?: string[]
  profile?: string
  target?: ImportProfileTarget
  created_materials?: number
  created_units?: number
  info?: string
}

// --- Document register movements viewer ---

export interface DocumentMovementsHeader {
  id: number
  number?: string | null
  date?: string | null
  kind: GoodsKind
  is_posted: boolean
  sum_with_vat: number
}

export interface InventoryMovementDocRow {
  line_number: number
  period: string
  material_id?: number | null
  material_code?: string | null
  material_name?: string | null
  object_id?: number | null
  object_name?: string | null
  unit_id?: number | null
  unit_name?: string | null
  quantity_income: number
  quantity_expense: number
  sum_income: number
  sum_expense: number
}

export interface SettlementMovementDocRow {
  line_number: number
  period: string
  direction: SettlementDirection
  organization_id?: number | null
  organization_name?: string | null
  counterparty_id?: number | null
  counterparty_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  object_id?: number | null
  object_name?: string | null
  accrual_amount: number
  payment_amount: number
  planned_amount: number
}

export interface DocumentMovements {
  document: DocumentMovementsHeader
  inventory: InventoryMovementDocRow[]
  settlements: SettlementMovementDocRow[]
  totals: {
    quantity_income: number
    quantity_expense: number
    sum_income: number
    sum_expense: number
    accrual_amount: number
    payment_amount: number
    planned_amount: number
  }
}

