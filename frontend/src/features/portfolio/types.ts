export type Asset = {
  account_id: string; code: string; name: string; market: string; asset_type: string; currency: string; unit: string;
  quantity: string; average_cost: string | null; cost: string | null; cost_cny: string | null;
  price: string | null; market_value: string | null; market_value_cny: string | null;
  floating: string | null; holding_return: string | null; realized: string | null; realized_cny: string | null;
  cycle: number; quote: { at: string; source: string; price_kind: string } | null;
};
export type Point = {
  observed_at: string; event_type: string; account_id: string; record_id: number | null;
  total_assets: string | null; cash_value: string | null; market_value: string | null; profit: string | null;
  cumulative_return: string | null; nav: string | null; units: string; interval: number; ended: boolean;
  external_flow: string | null; quality: string; issues: string[]; performance_issues: string[];
  asset_returns: Record<string, string | null>;
  positions: Asset[]; cash: Array<{ account_id: string; currency: string; amount: string }>;
  pending: Array<{ account_id: string; currency: string; amount: string; pending_id: string; kind: string }>;
  changes: { before_quantity: string; after_quantity: string; before_cost: string | null; after_cost: string | null; realized: string | null } | null;
  data: Record<string, unknown>;
};
export type RecordItem = { id: number; category: "trade" | "event"; kind: string; account_id: string; effective_at: string; data: Record<string, unknown>; is_void: boolean };
export type OpeningAsset = { code: string; name: string; market: string; currency: string; asset_type: string; unit: string; quantity: string; average_cost: string | null; price: string | null; price_at?: string; cost_cny_amount?: string | null };
export type Opening = { account_id: string; effective_at: string; included: boolean; included_at?: string | null; excluded_at?: string | null; positions: OpeningAsset[]; cash: Record<string, string>; liabilities?: Record<string, string>; fx: Record<string, { rate: string; at: string; source: string }>; source?: string };
export type Portfolio = { current: Point | null; points: Point[]; records: RecordItem[]; openings: Opening[]; currency: string; scope: string };
