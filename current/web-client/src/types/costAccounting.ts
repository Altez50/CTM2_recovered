export interface CostElement {
  id: number
  code: string
  name: string
  kind: string
  is_direct: boolean
  allocation_base_id: number | null
  is_predefined: boolean
  allocation_base_name?: string | null
}

export interface AllocationBase {
  id: number
  name: string
  kind: string
}

export interface Machine {
  id?: number
  name: string
  code: string
  cost_per_hour: number
  operator_rate_per_hour: number
  unit: string
  marked_for_deletion?: boolean
}

export interface MaterialConsumptionLine {
  id?: number
  document_id?: number
  line_number: number
  work_id: number | null
  material_id: number | null
  planned_quantity: number
  actual_quantity: number
  price: number
  sum: number
  cost_element_id: number | null
  unit?: string | null
  work_name?: string | null
  material_name?: string | null
}

export interface MaterialConsumption {
  id?: number
  uuid?: string | null
  number: string
  date: string
  object_id: number | null
  estimate_id: number | null
  foreman_id: number | null
  warehouse: string
  is_posted?: boolean
  posted_at?: string | null
  marked_for_deletion?: boolean
  based_on_type?: string | null
  based_on_id?: number | null
  based_on_number?: string | null
  lines: MaterialConsumptionLine[]
  object_name?: string | null
  estimate_number?: string | null
  foreman_name?: string | null
}

export interface MachineryUsageLine {
  id?: number
  document_id?: number
  line_number: number
  machine_id: number | null
  work_id: number | null
  hours: number
  machine_cost: number
  operator_labor: number
  unit?: string | null
  machine_name?: string | null
  work_name?: string | null
}

export interface MachineryUsageReport {
  id?: number
  uuid?: string | null
  number: string
  date: string
  object_id: number | null
  estimate_id: number | null
  foreman_id: number | null
  is_posted?: boolean
  posted_at?: string | null
  marked_for_deletion?: boolean
  based_on_type?: string | null
  based_on_id?: number | null
  based_on_number?: string | null
  lines: MachineryUsageLine[]
  object_name?: string | null
  estimate_number?: string | null
  foreman_name?: string | null
}

export interface SubcontractAcceptanceLine {
  id?: number
  document_id?: number
  line_number: number
  work_id: number | null
  counterparty_id: number | null
  sum: number
  description: string
  unit?: string | null
  work_name?: string | null
  counterparty_name?: string | null
}

export interface SubcontractAcceptance {
  id?: number
  uuid?: string | null
  number: string
  date: string
  object_id: number | null
  estimate_id: number | null
  is_posted?: boolean
  posted_at?: string | null
  marked_for_deletion?: boolean
  lines: SubcontractAcceptanceLine[]
  object_name?: string | null
  estimate_number?: string | null
}

export interface OverheadExpenseLine {
  id?: number
  document_id?: number
  line_number: number
  cost_element_id: number | null
  counterparty_id: number | null
  sum: number
  description: string
  cost_element_name?: string | null
  counterparty_name?: string | null
}

export interface OverheadExpense {
  id?: number
  uuid?: string | null
  number: string
  date: string
  period: string
  is_distributed?: boolean
  marked_for_deletion?: boolean
  lines: OverheadExpenseLine[]
}

export type CalculationStatus = 'draft' | 'calculated' | 'posted'

export interface CostCalculation {
  id?: number
  uuid?: string | null
  number: string
  period: string
  date: string
  object_id: number
  status?: CalculationStatus
  marked_for_deletion?: boolean
  object_name?: string | null
}

export interface OverheadDistributionRequest {
  period: string
  allocation_base_id: number
  object_id: number
}

export interface OverheadDistributionResult {
  period: string
  allocation_base_name: string
  total_distributed: number
  record_count: number
}

export interface CostElementSummary {
  cost_element_id: number
  cost_element_name: string
  cost_element_kind: string
  planned_amount: number
  actual_amount: number
  deviation: number
}

export interface WorkCostRow {
  work_id: number
  work_name: string | null
  completed_quantity: number
  planned_cost: number
  actual_cost: number
  deviation: number
  contract_value: number
  profit: number
  profitability_pct: number
}

export interface CostCardResponse {
  object_id: number
  object_name: string | null
  period_from: string | null
  period_to: string | null
  elements: CostElementSummary[]
  total_planned: number
  total_actual: number
  total_deviation: number
  total_contract_value: number
  total_profit: number
  profitability_pct: number
  works: WorkCostRow[]
}

export interface TurnoverRow {
  cost_element_id: number
  cost_element_name: string
  cost_element_kind: string
  opening_balance: number
  inflow: number
  outflow: number
  closing_balance: number
}

export interface TurnoverReportResponse {
  period_from: string
  period_to: string
  object_id: number
  object_name: string | null
  rows: TurnoverRow[]
}

export interface DeviationRow {
  work_id: number
  work_name: string | null
  cost_element_name: string
  planned_amount: number
  actual_amount: number
  deviation: number
  deviation_pct: number
}

export interface DeviationsReportResponse {
  period: string
  object_id: number
  threshold_pct: number
  rows: DeviationRow[]
}

export interface ProfitabilityRow {
  object_id?: number
  object_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  counterparty_name?: string | null
  planned_cost: number
  actual_cost: number
  contract_value: number
  profit: number
  profitability_pct: number
}

export interface ProfitabilityReportResponse {
  period?: string | null
  group_by?: string
  rows: ProfitabilityRow[]
}

export interface LimitCheckRequest {
  work_id: number
  material_id: number
  actual_quantity: number
  completed_quantity: number
}

export interface LimitCheckResponse {
  work_id: number
  material_id: number
  planned_quantity: number
  actual_quantity: number
  limit_exceeded: boolean
  exceed_pct: number
}

// ── Drilldown (COST_DRILLDOWN_SPEC.md §6.5) ───────────────────────────────

export interface DrilldownQuery {
  period_from?: string
  period_to?: string
  period_before?: string
  object_id?: number
  cost_element_id?: number
  work_id?: number
  estimate_id?: number
  contract_id?: number
  amount_sign?: 'positive' | 'negative'
  registrar_type?: string
  page?: number
  page_size?: number
}

export interface DrilldownItem {
  id: number
  period: string
  date?: string
  registrar_type?: string
  registrar_id?: number
  registrar_number?: string | null
  object_id?: number | null
  object_name?: string | null
  work_id?: number | null
  work_name?: string | null
  cost_element_id?: number
  cost_element_name?: string
  quantity: number
  amount: number
  allocation_base_id?: number | null
  allocation_base_name?: string | null
  base_value?: number | null
}

export interface DrilldownResponse {
  items: DrilldownItem[]
  totals: { quantity: number; amount: number }
}
