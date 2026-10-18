export type Asset = {
  account_id: string; code: string; name: string; market: string; asset_type: string; currency: string; unit: string;
  account_positions?: Asset[];
  quantity: string; diluted_cost: string | null; cost_method: "diluted"; dividends: string; dividends_cny: string | null; average_cost: string | null; cost: string | null; cost_cny: string | null;
  price: string | null; market_value: string | null; market_value_cny: string | null;
  floating: string | null; holding_return: string | null; realized: string | null; realized_cny: string | null;
  cycle: number; quote: { at: string; source: string; price_kind: string } | null;
  position_weight: string | null; closed_return: string | null;
  closed_cycles: Array<{ cycle: number; opened_at: string; closed_at: string; realized: string | null; disposed_cost: string | null; return: string | null }>;
};
export type Point = {
  observed_at: string; event_type: string; account_id: string; record_id: number | null;
  valuation_date?: string | null;
  total_assets: string | null; cash_value: string | null; market_value: string | null; profit: string | null;
  opening_assets: string | null; net_flows: string;
  cumulative_return: string | null; nav: string | null; units: string; interval: number; ended: boolean;
  external_flow: string | null; quality: string; issues: string[]; performance_issues: string[];
  asset_returns: Record<string, string | null>;
  positions: Asset[]; cash: Array<{ account_id: string; currency: string; amount: string }>;
  pending: Array<{ account_id: string; currency: string; amount: string; pending_id: string; kind: string }>;
  changes: { before_quantity: string; after_quantity: string; before_cost: string | null; after_cost: string | null; realized: string | null } | null;
  data: Record<string, unknown>;
};
export type ChartPoint = Pick<Point, "observed_at" | "event_type" | "record_id" | "account_id" | "interval" | "ended" | "total_assets" | "nav" | "units" | "profit" | "opening_assets" | "cumulative_return" | "asset_returns" | "valuation_date"> & {
  transaction?: { code: string; name: string; side: string; quantity: string; price: string; fees: string; currency: string; unit: string };
};
export type RecordItem = { id: number; category: "trade" | "event"; kind: string; account_id: string; effective_at: string; data: Record<string, unknown>; is_void: boolean };
export type OpeningAsset = { code: string; name: string; market: string; currency: string; asset_type: string; unit: string; quantity: string; average_cost: string | null; price: string | null; price_at?: string; cost_cny_amount?: string | null };
export type Opening = { account_id: string; effective_at: string; included: boolean; included_at?: string | null; excluded_at?: string | null; positions: OpeningAsset[]; cash: Record<string, string>; liabilities?: Record<string, string>; fx: Record<string, { rate: string; at: string; source: string }>; source?: string };
export type Portfolio = { current: Point | null; points: ChartPoint[]; records: RecordItem[]; openings: Opening[]; currency: string; scope: string; account_names?: Record<string, string>; holdings: Asset[]; allocation: Array<{ type: string; weight: string }>; coverage: { included_accounts: string[]; unenrolled_accounts: string[] } };

export type Reconciliation = { code: string; currency: string; source_at: string; status: "mismatch" | "uncovered"; reason: string;
  source_quantity: string; ledger_quantity: string | null; source_average_cost: string | null; ledger_average_cost: string | null };
export type HistoryEntry = { kind: string; effective_at: string; data: Record<string, unknown> };
export type HistoryPreview = { checkpoint_at: string; new_start: string; record_count: number; current: Point;
  differences: Array<{ item: string; before: string | null; after: string | null }> };

export type ClosedTrade = { cash_amount: string; gross_amount: string; record_id: string; at: string; side: string; quantity: string; price: string; fees: string; disposed_cost: string | null; realized: string | null };
export type ClosedPosition = { buy_total: string | null; sell_total: string; trading_profit: string | null; dividends: string; dividend_records: Array<{record_id: string; at: string; amount: string; currency: string}>; account_id: string; account_name: string; code: string; name: string; currency: string; unit: string; cycle: number; opened_at: string; closed_at: string; holding_days: number | null; realized: string | null; realized_cny: string | null; disposed_cost: string | null; return: string | null; opening_kind: string; trades: ClosedTrade[] };
export type ClosedQuery = { items: ClosedPosition[]; summary: { count: number; symbol_count: number; win_rate: string | null; known_count: number; unknown_count: number; realized_cny: string | null; known_realized_cny: string; missing_cny_count: number; by_currency: Record<string, string> } };
