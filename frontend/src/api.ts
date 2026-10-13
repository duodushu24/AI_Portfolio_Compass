export type SyncStatus = {
  sync_id?: string;
  sync_type?: string;
  status: string;
  start_time?: string;
  end_time?: string;
  last_error?: string;
  inserted_count?: number;
  updated_count?: number;
};

export type HealthStatus = {
  service: string;
  database: string;
  opend: string;
  sqlite_encryption_ready: boolean;
  local_data?: {
    accounts: number;
    account_snapshots: number;
    positions: number;
    deals: number;
    empty: boolean;
  };
  demo_mode?: boolean;
  workspace?: "formal" | "demo";
  futu?: {
    host: string;
    port: number;
    opend_connected: boolean;
    account_access: boolean;
    account_count: number;
    message: string;
  };
  ai?: {
    provider: string;
    display_name?: string;
    model: string;
    configured: boolean;
    enabled?: boolean;
    source?: string;
  };
};

export type AIProviderTemplate = {
  provider: string;
  label: string;
  default_base_url: string;
  default_model: string;
  models: string[];
  openai_compatible: boolean;
  help_text?: string;
};

export type AIRuntimeConfig = {
  provider: string;
  display_name: string;
  base_url: string;
  model: string;
  enabled: boolean;
  has_api_key: boolean;
  masked_api_key: string;
  last_test_status: string;
  last_test_message: string;
  updated_at?: string | null;
  source?: string;
};

export type AIConfigResponse = {
  runtime: AIRuntimeConfig;
  providers: AIProviderTemplate[];
  scenes: Array<{
    scene: string;
    label: string;
    provider: string;
    model: string;
    system_prompt: string;
    default_model: string;
    default_prompt: string;
    updated_at?: string | null;
  }>;
};

export type DecisionCard = {
  card_id: string;
  code: string;
  position_layer: string;
  recommendation: string;
  confidence: string;
  reasons: string[];
  risks: string[];
  key_prices: Record<string, number | null>;
  status: string;
  priority: string;
  data_time: string;
  action_required: boolean;
  generation_source: string;
  model: string;
  generated_at: string;
  input_version: string;
  analysis_framework: {
    layer?: string;
    focus?: string[];
  };
  missing_data: string[];
  invalid_conditions: string[];
  needs_regeneration: boolean;
  merged_count: number;
  merged_first_data_time: string;
  merged_last_data_time: string;
};

export type Position = {
  cost_method?: "average" | "unknown";
  cost_cny_amount?: string | null;
  account_id: string;
  code: string;
  name: string;
  market: string;
  asset_type: string;
  quantity: number;
  current_price: number;
  average_cost: number;
  raw_market_value: number;
  raw_currency: string;
  normalized_market_value: number;
  normalized_currency: string;
  exchange_rate_to_base?: number | null;
  position_weight: number;
  profit_loss_ratio: number;
  position_layer: string;
  layer_source: string;
  layer_confidence: string;
  layer_reason: string;
  missing_market_code: boolean;
  account_count?: number;
  account_positions?: Array<Partial<Position> & { account_id: string; market_value: number; currency: string; quantity: number; weight: number }>;
  snapshot_time: string;
};

export type PositionSnapshotPayload = {
  save_mode?: "new" | "correction";
  cost_method?: "average" | "unknown";
  cost_cny_amount?: string | null;
  original_code?: string;
  original_snapshot_time?: string;
  code: string;
  name: string;
  market: string;
  asset_type: string;
  quantity: number;
  average_cost: number;
  current_price: number;
  market_value?: number | null;
  currency: string;
  normalized_market_value?: number | null;
  normalized_currency: string;
  exchange_rate_to_base?: number | null;
  profit_loss_ratio?: number | null;
  position_weight?: number | null;
  position_layer: string;
  snapshot_time: string;
};

export type AccountSummary = {
  ledger_enrolled?: boolean;
  account_id: string;
  source_name: string;
  broker_provider?: string;
  display_name: string;
  institution: string;
  import_mode: string;
  import_modes?: string[];
  position_import_modes?: string[];
  review_import_modes?: string[];
  market_data_provider?: string;
  news_data_provider?: string;
  account_type?: string;
  markets?: string[];
  enabled: boolean;
  base_currency: string;
  total_assets: number;
  cash: number;
  market_value: number;
  display_currency: string;
  display_total_assets: number;
  last_sync_time?: string | null;
  snapshot_time: string;
};

export type ImportPreview = {
  holding_completeness?: "partial" | "full";
  holding_market?: string;
  holding_observed_at?: string;
  confirm_average_cost?: boolean;
  source_name: string;
  filename: string;
  import_hash: string;
  account: Record<string, unknown>;
  account_snapshot: Record<string, unknown>;
  positions: Position[];
  position_count: number;
  deals: AccountDeal[];
  deal_count: number;
  total_assets: number;
  market_value: number;
  cash: number;
  snapshot: Record<string, unknown>;
  errors?: string[];
  warnings?: string[];
  can_confirm?: boolean;
};

export type AccountDeal = {
  deal_id: string;
  order_id: string;
  code: string;
  side: string;
  price: number;
  quantity: number;
  deal_time?: string | null;
  market: string;
  account_id: string;
  raw_payload: Record<string, unknown>;
};

export type ProviderState = {
  provider: string;
  provider_label: string;
  data_type: "quote" | "news" | "announcement" | "filing" | string;
  market: string;
  status: string;
  message: string;
  checked_at?: string | null;
  last_success_time?: string | null;
  freshness_seconds?: number;
  license_note?: string;
  capabilities?: Array<Record<string, unknown>>;
};

export type DealPayload = {
  original_deal_id?: string;
  deal_id: string;
  order_id?: string;
  code: string;
  side?: string;
  price: number;
  quantity: number;
  deal_time?: string | null;
  market?: string;
};

export type AccountDataOverview = {
  ledger_enrolled?: boolean;
  reconciliation?: Array<{ code: string; source_quantity: string; ledger_quantity: string }>;
  account: AccountSummary;
  asset_snapshot: {
    account_id: string;
    total_assets: number;
    cash: number;
    market_value: number;
    currency: string;
    raw_currency_values: Record<string, unknown>;
    snapshot_time: string;
    sync_id: string;
  } | null;
  positions: Position[];
  deals: AccountDeal[];
  updated_at: {
    account?: string | null;
    position?: string | null;
    deal?: string | null;
    quote?: string | null;
    news?: string | null;
  };
  provider_states: ProviderState[];
};

export type AIAnalysis = {
  analysis_id: string;
  code: string;
  provider: string;
  model: string;
  output: {
    recommendation?: string;
    conclusion?: string;
    reasons?: string[];
    risks?: string[];
    invalid_conditions?: string[];
    missing_data?: string[];
  };
  status: string;
  error_message: string;
  data_version: string;
  created_at: string;
};

export type NewsItem = {
  news_id: string;
  code: string;
  provider: string;
  market: string;
  news_type: string;
  title: string;
  news_sub_type: string;
  source: string;
  publish_time?: string | null;
  view_count: number;
  related_securities: Array<Record<string, unknown>>;
  url: string;
  fetched_at: string;
};

export type KLineItem = {
  time_key: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  turnover: number;
};

export type KLineResponse = {
  code: string;
  ktype: string;
  status: string;
  message: string;
  items: KLineItem[];
};

export type Profile = {
  empty: boolean;
  confidence?: string;
  generated_at?: string;
  ratios?: Record<string, number>;
  tags?: string[];
  change_reason?: string;
  message?: string;
};

export type InvestorPreference = {
  empty: boolean;
  preference_id?: string;
  account_id: string;
  kyc_profile: Record<string, unknown>;
  kyc_completeness?: {
    filled_count: number;
    total_count: number;
    ratio: number;
    filled_fields: string[];
    missing_fields: string[];
    values: Record<string, unknown>;
  };
  risk_tolerance: string;
  investment_horizon: string;
  liquidity_needs: string;
  target_return: string;
  notes: string;
  updated_at?: string | null;
};

export type WorkflowStep = {
  step_no: number;
  title: string;
  detail: string;
  action_type: string;
  action_label: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  artifact_ids: string[];
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  agent_note?: string;
  expected_observation?: string;
  observation?: Record<string, unknown>;
};

export type WorkflowArtifact = {
  artifact_id: string;
  type: "donut" | "bar" | string;
  title: string;
  data: Array<{ label: string; value: number; examples?: string }>;
};

export type AIWorkflowRun = {
  run_id: string;
  workflow_type: "customer_profile" | "portfolio_diagnosis" | "asset_allocation";
  workflow_label: string;
  account_id: string;
  question: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  steps: WorkflowStep[];
  input_context: Record<string, unknown>;
  output: {
    title?: string;
    markdown?: string;
    partial_markdown?: string;
    summary?: string;
    home_summary_cards?: Array<{
      key: string;
      label: string;
      tone?: "info" | "ok" | "watch" | "risk";
      summary?: string;
      value?: string;
      items?: Array<{ text: string; reason?: string; code?: string }>;
      source?: "ai_report" | "local_rules";
    }>;
    agent_mode?: string;
    tool_trace?: Array<Record<string, unknown>>;
    calculation_audit_pack?: Record<string, unknown>;
    calculation_audit_result?: Record<string, unknown>;
    chapter_statuses?: Array<Record<string, unknown>>;
    validation_result?: Record<string, unknown>;
    quality_status?: "ok" | "needs_review";
    quality_issues?: string[];
    warnings?: string[];
  };
  artifacts: WorkflowArtifact[];
  provider: string;
  model: string;
  data_version: string;
  error_message: string;
  created_at: string;
  updated_at: string;
};

export type Review = {
  empty: boolean;
  review_date?: string;
  portfolio_summary?: Record<string, number | string>;
  advice_summary?: Record<string, unknown>;
  user_action_summary?: Record<string, unknown>;
  result_summary?: Record<string, unknown>;
  next_watchlist?: string[];
  message?: string;
};

export type TradeReview = {
  review_id: string;
  account_id: string;
  deal_id: string;
  order_id: string;
  code: string;
  side: string;
  price: number;
  quantity: number;
  deal_time?: string;
  one_day_price?: number | null;
  five_day_price?: number | null;
  latest_price?: number | null;
  one_day_return?: number | null;
  five_day_return?: number | null;
  latest_return?: number | null;
  result_label: string;
  discipline_label: string;
  confidence: string;
  fact_summary: Record<string, unknown>;
  ai_commentary: string;
  user_note: string;
  intent_tags: TradeIntentTags;
  intent_plan: TradeIntentPlan;
  generated_by: string;
  created_at: string;
  updated_at: string;
};

export type TradeIntentTags = {
  trend: string[];
  market: string[];
  fundamental: string[];
  emotion: string[];
};

export type TradeIntentPlan = {
  holding_period?: string;
  stop_loss_type?: string;
  take_profit_type?: string;
  stop_loss_price?: string;
  take_profit_price?: string;
};

export type TradeReviewList = {
  empty: boolean;
  summary: {
    trade_count: number;
    waiting_count: number;
    risk_count: number;
    planned_count: number;
    missing_note_count: number;
    missing_intent_count?: number;
  };
  items: TradeReview[];
};

export type Dashboard = {
  sync: SyncStatus;
  portfolio: {
    account_id: string;
    account_count: number;
    position_count: number;
    total_assets: number;
    total_position_value: number;
    cash: number;
    base_currency: string;
    display_currencies: string[];
    display_rates: Record<string, number>;
    display_rate_meta: Record<string, { source: string; rate_time?: string | null; fetched_at?: string | null; expires_at?: string | null; is_stale: boolean }>;
    cash_ratio: number;
    max_position_weight: number;
    max_account_weight: number;
    accounts: AccountSummary[];
  };
  action_cards: DecisionCard[];
  decision_card_state: {
    total_positions: number;
    card_count: number;
    missing_codes: string[];
    stale_codes: string[];
    legacy_codes: string[];
    needs_generation: boolean;
  };
  freshness: FreshnessItem[];
  empty: boolean;
};

export type FreshnessItem = {
  data_type: string;
  status: "fresh" | "stale" | "missing";
  age_seconds: number | null;
  valid_seconds: number;
  message: string;
  stale_action: string;
};

export type WorkspaceMode = "formal" | "demo";

export type DiaryInput = {
  record_date: string;
  title: string;
  body: string;
  topics: string[];
  keywords: string[];
};

export type InvestmentDiary = DiaryInput & {
  id: number;
  source_type: string;
  created_at: string;
  updated_at: string;
  markdown_path: string;
  markdown_saved: boolean;
};

export type DiaryList = { items: InvestmentDiary[]; count: number; root: string };
export type DiarySaveResult = {
  item: InvestmentDiary;
  database_saved: boolean;
  markdown_saved: boolean;
  message: string;
  file_errors: string[];
};

export type InvestmentTagInput = { name: string; definition: string; aliases: string[] };
export type InvestmentTag = InvestmentTagInput & { id: number };
export type DiaryCandidate = { title: string; body: string; keywords: string[]; tag_ids: number[]; new_tags: InvestmentTagInput[]; accepted_new_tags: number[] };
export type DiarySummaryInput = DiaryCandidate & {
  record_date: string; diary_ids: number[]; session_ids: number[];
  source_type: "in_app_ai" | "external_discussion" | "manual"; source_note: string; confirmed: boolean;
};
export type DiarySummary = Omit<DiarySummaryInput, "tag_ids" | "new_tags" | "accepted_new_tags" | "confirmed"> & {
  id: number; tags: InvestmentTag[]; markdown_path: string; markdown_saved: boolean; created_at: string; updated_at: string;
};
export type SummarySaveResult = { item: DiarySummary; database_saved: boolean; markdown_saved: boolean; message: string; file_errors: string[] };
export type DiaryChatMessage = {
  id: number; sequence: number; role: "user" | "assistant"; task: "analyze" | "discuss" | "summarize";
  body: string; status: string; reply_to_id: number | null; provider: string; model: string; created_at: string;
};
export type DiaryDiscussion = {
  id: number; record_date: string; diary_ids: number[]; title: string; question: string; background: string; base_source: string;
  candidate: Partial<DiaryCandidate>; needs_summary: boolean; generation_status: string; last_error: string;
  created_at: string; updated_at: string; messages?: DiaryChatMessage[];
};

const WORKSPACE_STORAGE_KEY = "portfolio_workspace";
const FORMAL_API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8010";
const DEMO_API_BASE = import.meta.env.VITE_DEMO_API_BASE ?? "http://127.0.0.1:8011";

function currentWorkspace(): WorkspaceMode {
  return localStorage.getItem(WORKSPACE_STORAGE_KEY) === "demo" ? "demo" : "formal";
}

function apiBase() {
  return currentWorkspace() === "demo" ? DEMO_API_BASE : FORMAL_API_BASE;
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const base = apiBase();
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...(options?.headers ?? {}) },
      ...options,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "网络请求失败";
    throw new Error(`无法连接${currentWorkspace() === "demo" ? "演示" : "正式"}工作区：${message}`);
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromResponse(text) || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function downloadFile(path: string, fallbackFilename: string) {
  const base = apiBase();
  let response: Response;
  try {
    response = await fetch(`${base}${path}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "网络请求失败";
    throw new Error(`无法连接${currentWorkspace() === "demo" ? "演示" : "正式"}工作区：${message}`);
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromResponse(text) || `HTTP ${response.status}`);
  }

  const blob = await response.blob();
  const filename = filenameFromDisposition(response.headers.get("content-disposition")) || fallbackFilename;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function errorMessageFromResponse(text: string) {
  if (!text) return "";
  try {
    const payload = JSON.parse(text);
    if (typeof payload?.detail === "string") return payload.detail;
    if (payload?.detail?.message) return String(payload.detail.message);
  } catch {
    return text;
  }
  return text;
}

function filenameFromDisposition(disposition: string | null) {
  if (!disposition) return "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded?.[1]) return decodeURIComponent(encoded[1].replace(/"/g, ""));
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  return plain?.[1] ?? "";
}

export type ReturnDraftItem = {
  position_id: number; account_id: string; code: string; name: string;
  quantity: number; average_cost: number; raw_currency: string; snapshot_time: string;
  cost_method: string; confirm_average_cost: boolean; cost_cny_amount: string | null;
  price: string | null; price_at: string; fx_rate: string | null; source: string; price_kind: "price" | "nav" | "estimate";
};
export type ReturnPriceInput = Pick<ReturnDraftItem, "position_id" | "account_id" | "code" | "confirm_average_cost" | "cost_cny_amount" | "price" | "price_at" | "fx_rate" | "source" | "price_kind"> & {
  holding_quantity?: string; holding_average_cost?: string; holding_currency?: string; price_currency?: string;
};
export type ReturnPayload = { observed_at: string; account_ids: string[]; currency: string; note: string; inputs: ReturnPriceInput[] };
export type ReturnItem = {
  position_id: number; account_id: string; code: string; name: string; quantity: string | null; average_cost: string | null;
  raw_currency: string; cost_method: string; cost: string | null; price: string | null; price_at: string | null;
  source: string; price_kind: string; fx_rate: string | null; market_value: string | null;
  pnl: string | null; return_ratio: string | null; problems: string[]; stale: boolean;
};
export type ReturnPoint = {
  id: number; observed_at: string; account_ids: string[]; currency: string; note: string;
  inputs: ReturnPriceInput[]; items: ReturnItem[]; return_ratio: string | null;
  status: string; holding_count: number; covered_count: number; price_warning: boolean; holdings_changed: boolean;
  asset_returns: Record<string, string | null>;
  scope_warning: boolean;
};
export type ReturnEvent = { id: number; account_id: string; code: string; side: string; quantity: number; price: number; deal_time: string;
  fees: Record<string, number | null>; before: { quantity: number; average_cost: number; observed_at: string } | null;
  after: { quantity: number; average_cost: number | null; observed_at: string } | null; detail_note: string };
export type ReturnSeries = { account_ids: string[]; available_scopes: string[][]; currency: string; items: ReturnPoint[]; events: ReturnEvent[]; other_scope_count: number; cumulative_available: boolean; cumulative_reason: string };
export type HoldingHistoryItem = Position & { id: number; is_void: boolean; is_current: boolean; completeness: string; batch_id: number | null };
export type HoldingBatch = { id: number; account_id: string; market: string; completeness: string; observed_at: string; source: string };

export const api = {
  returnDraft: (accountId: string, observedAt: string, currency: string, accountIds?: string[]) => {
    const query = new URLSearchParams({ account_id: accountId, observed_at: observedAt, currency });
    accountIds?.forEach(id => query.append("account_ids", id));
    return request<{ account_ids: string[]; items: ReturnDraftItem[] }>(`/api/returns/draft?${query}`);
  },
  returnSeries: (accountId: string, currency: string, start = "", end = "", accountIds?: string[]) => {
    const query = new URLSearchParams({ account_id: accountId, currency });
    if (start) query.set("start", start);
    if (end) query.set("end", end);
    accountIds?.forEach(id => query.append("account_ids", id));
    return request<ReturnSeries>(`/api/returns/series?${query}`);
  },
  saveReturn: (payload: ReturnPayload, id?: number) => request<{ item: ReturnPoint }>(`/api/returns/observations${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(payload) }),
  deleteReturn: (id: number) => request(`/api/returns/observations/${id}`, { method: "DELETE" }),
  holdingHistory: (accountId: string, at = "") => request<{ items: HoldingHistoryItem[]; batches: HoldingBatch[]; current_ids: number[] }>(`/api/returns/history?account_id=${encodeURIComponent(accountId)}${at ? `&at=${encodeURIComponent(at)}` : ""}`),
  confirmEmptyHoldings: (accountId: string, observedAt: string, market: string) => request(`/api/returns/accounts/${encodeURIComponent(accountId)}/empty`, { method: "POST", body: JSON.stringify({ observed_at: observedAt, market, confirmation: "EMPTY_SCOPE" }) }),
  workspace: currentWorkspace,
  setWorkspace: (workspace: WorkspaceMode) => localStorage.setItem(WORKSPACE_STORAGE_KEY, workspace),
  health: () => request<HealthStatus>("/api/health"),
  aiProviders: () => request<{ items: AIProviderTemplate[] }>("/api/ai/providers"),
  aiConfig: () => request<AIConfigResponse>("/api/ai/config"),
  saveAIConfig: (payload: Partial<AIRuntimeConfig> & { api_key?: string; scenes?: AIConfigResponse["scenes"] }) =>
    request<AIConfigResponse>("/api/ai/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testAIConfig: (payload: Partial<AIRuntimeConfig> & { api_key?: string }) =>
    request<{ status: string; message: string; runtime: AIRuntimeConfig; output?: Record<string, unknown> }>("/api/ai/config/test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  accounts: () => request<{ items: AccountSummary[]; count: number }>("/api/accounts"),
  createAccount: (account: Partial<AccountSummary>) =>
    request<{ account: AccountSummary }>("/api/accounts", {
      method: "POST",
      body: JSON.stringify(account),
    }),
  updateAccount: (accountId: string, account: Partial<AccountSummary>) =>
    request<{ account: AccountSummary }>(`/api/accounts/${encodeURIComponent(accountId)}`, {
      method: "PATCH",
      body: JSON.stringify(account),
    }),
  deleteAccount: (accountId: string, confirmWithData = false) =>
    request<{ status: string; data_counts: Record<string, number> }>(`/api/accounts/${encodeURIComponent(accountId)}?confirm_with_data=${confirmWithData ? "true" : "false"}`, {
      method: "DELETE",
    }),
  dashboard: (accountId = "all") => request<Dashboard>(`/api/dashboard?account_id=${encodeURIComponent(accountId)}`),
  review: (accountId = "all") => request<Review>(`/api/review?account_id=${encodeURIComponent(accountId)}`),
  diaries: (filters: { start_date?: string; end_date?: string; q?: string; offset?: number; limit?: number } = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
    return request<DiaryList>(`/api/diaries?${params.toString()}`);
  },
  diary: (id: number) => request<{ item: InvestmentDiary }>(`/api/diaries/${id}`),
  saveDiary: (input: DiaryInput, id?: number) => request<DiarySaveResult>(id ? `/api/diaries/${id}` : "/api/diaries", {
    method: id ? "PUT" : "POST", body: JSON.stringify(input),
  }),
  retryDiaryMarkdown: (id: number) => request<DiarySaveResult>(`/api/diaries/${id}/retry-markdown`, { method: "POST" }),
  investmentTags: () => request<{ items: InvestmentTag[] }>("/api/investment-tags"),
  saveInvestmentTag: (input: InvestmentTagInput, id?: number) => request<{ item: InvestmentTag; file_errors?: string[] }>(id ? `/api/investment-tags/${id}` : "/api/investment-tags", { method: id ? "PUT" : "POST", body: JSON.stringify(input) }),
  mergeInvestmentTag: (id: number, targetId: number) => request<{ item: InvestmentTag; file_errors: string[] }>(`/api/investment-tags/${id}/merge`, { method: "POST", body: JSON.stringify({ target_id: targetId }) }),
  diarySummaries: (filters: { start_date?: string; end_date?: string; q?: string; tag_id?: number; offset?: number; limit?: number } = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
    return request<{ items: DiarySummary[]; count: number }>(`/api/diary-summaries?${params}`);
  },
  saveDiarySummary: (input: DiarySummaryInput, id?: number) => request<SummarySaveResult>(id ? `/api/diary-summaries/${id}` : "/api/diary-summaries", { method: id ? "PUT" : "POST", body: JSON.stringify(input) }),
  retrySummaryMarkdown: (id: number) => request<SummarySaveResult>(`/api/diary-summaries/${id}/retry-markdown`, { method: "POST" }),
  diaryDiscussions: (date?: string, offset = 0) => request<{ items: DiaryDiscussion[]; count: number }>(`/api/diary-discussions?${new URLSearchParams({ ...(date ? { record_date: date } : {}), offset: String(offset) })}`),
  diaryDiscussion: (id: number) => request<{ item: DiaryDiscussion }>(`/api/diary-discussions/${id}`),
  createDiaryDiscussion: (input: { record_date: string; diary_ids: number[]; title: string; question: string; background: string; base_summary_id?: number }) => request<{ item: DiaryDiscussion }>("/api/diary-discussions", { method: "POST", body: JSON.stringify(input) }),
  saveDiaryCandidate: (id: number, candidate: DiaryCandidate) => request<{ item: DiaryDiscussion }>(`/api/diary-discussions/${id}`, { method: "PUT", body: JSON.stringify(candidate) }),
  addDiaryMessage: (id: number, task: DiaryChatMessage["task"], body: string) => request<{ item: DiaryDiscussion; message_id: number }>(`/api/diary-discussions/${id}/messages`, { method: "POST", body: JSON.stringify({ task, body }) }),
  generateDiaryReply: (id: number, messageId: number, task: DiaryChatMessage["task"], consent: boolean) => request<{ item: DiaryDiscussion }>(`/api/diary-analysis/${task}`, { method: "POST", body: JSON.stringify({ session_id: id, message_id: messageId, consent_external_ai: consent }) }),
  suggestDiaryTags: (body: string, consent: boolean) => request<Pick<DiaryCandidate, "tag_ids" | "new_tags">>("/api/diary-analysis/suggest-tags", { method: "POST", body: JSON.stringify({ body, consent_external_ai: consent }) }),
  tradeReviews: (accountId = "all") => request<TradeReviewList>(`/api/review/trades?account_id=${encodeURIComponent(accountId)}`),
  refreshTradeReviewMarketData: (accountId = "all") => request<{ status: string; message: string; summary: TradeReviewList["summary"] }>(`/api/review/trades/refresh-market-data?account_id=${encodeURIComponent(accountId)}`, { method: "POST" }),
  updateTradeReviewIntent: (reviewId: string, note: string, tags: TradeIntentTags, plan: TradeIntentPlan) =>
    request(`/api/review/trades/${encodeURIComponent(reviewId)}/intent`, {
      method: "PATCH",
      body: JSON.stringify({ note, tags, plan }),
    }),
  profile: (accountId = "all") => request<Profile>(`/api/profile?account_id=${encodeURIComponent(accountId)}`),
  profilePreferences: (accountId = "all") => request<InvestorPreference>(`/api/profile/preferences?account_id=${encodeURIComponent(accountId)}`),
  saveProfilePreferences: (accountId: string, preference: Partial<InvestorPreference>) =>
    request<InvestorPreference>(`/api/profile/preferences?account_id=${encodeURIComponent(accountId)}`, {
      method: "PATCH",
      body: JSON.stringify(preference),
    }),
  profileWorkflows: (accountId = "all") => request<{ items: AIWorkflowRun[]; count: number }>(`/api/profile/ai-workflows?account_id=${encodeURIComponent(accountId)}`),
  createProfileWorkflow: (workflowType: AIWorkflowRun["workflow_type"], accountId = "all", consentExternalAi = false, question = "", model?: string, systemPrompt?: string) =>
    request<{ run: AIWorkflowRun }>(`/api/profile/ai-workflows/${encodeURIComponent(workflowType)}?account_id=${encodeURIComponent(accountId)}`, {
      method: "POST",
      body: JSON.stringify({ consent_external_ai: consentExternalAi, use_external_model: consentExternalAi, question, model, system_prompt: systemPrompt }),
    }),
  profileWorkflowDetail: (runId: string) => request<{ run: AIWorkflowRun }>(`/api/profile/ai-workflows/${encodeURIComponent(runId)}`),
  cancelProfileWorkflow: (runId: string) =>
    request<{ run: AIWorkflowRun }>(`/api/profile/ai-workflows/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
    }),
  deleteProfileWorkflow: (runId: string) =>
    request<{ status: string }>(`/api/profile/ai-workflows/${encodeURIComponent(runId)}/delete`, {
      method: "POST",
    }),
  profileWorkflowDownloadUrl: (runId: string) => `${apiBase()}/api/profile/ai-workflows/${encodeURIComponent(runId)}/download`,
  profileWorkflowStreamUrl: (runId: string) => `${apiBase()}/api/profile/ai-workflows/${encodeURIComponent(runId)}/stream`,
  accountDataOverview: (accountId: string) => request<AccountDataOverview>(`/api/data/accounts/${encodeURIComponent(accountId)}/overview`),
  checkAccountProvider: (accountId: string, payload: { data_type: string; market?: string; provider?: string }) =>
    request<{ provider_states: ProviderState[]; status: string; message: string }>(`/api/data/accounts/${encodeURIComponent(accountId)}/providers/check`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  pullAccountMarketData: (accountId: string, payload: { data_type: "quote" | "news" | string }) =>
    request<{ provider_states: ProviderState[]; status: string; message: string; inserted_count: number; updated_count: number }>(`/api/data/accounts/${encodeURIComponent(accountId)}/market-data/pull`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  saveAccountPosition: (accountId: string, payload: PositionSnapshotPayload) =>
    request<{ status: string; overview: AccountDataOverview }>(`/api/data/accounts/${encodeURIComponent(accountId)}/positions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteAccountPosition: (accountId: string, code: string, snapshotTime: string) => {
    const params = new URLSearchParams({ code, snapshot_time: snapshotTime });
    return request<{ status: string; overview: AccountDataOverview }>(`/api/data/accounts/${encodeURIComponent(accountId)}/positions?${params.toString()}`, {
      method: "DELETE",
    });
  },
  saveAccountDeal: (accountId: string, payload: DealPayload) =>
    request<{ status: string; overview: AccountDataOverview }>(`/api/data/accounts/${encodeURIComponent(accountId)}/deals`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteAccountDeal: (accountId: string, dealId: string) =>
    request<{ status: string; overview: AccountDataOverview }>(`/api/data/accounts/${encodeURIComponent(accountId)}/deals/${encodeURIComponent(dealId)}`, {
      method: "DELETE",
    }),
  positions: (layer?: string, accountId = "all") => {
    const params = new URLSearchParams();
    params.set("account_id", accountId);
    if (layer) params.set("layer", layer);
    return request<{ items: Position[]; count: number }>(`/api/positions?${params.toString()}`);
  },
  positionDetail: (code: string, accountId = "all") => request<{ position: Position; account_positions: Position[]; cards: DecisionCard[]; news: NewsItem[]; ai_analysis: AIAnalysis | null }>(`/api/positions/${encodeURIComponent(code)}?account_id=${encodeURIComponent(accountId)}`),
  positionKLine: (code: string, accountId = "all", ktype = "K_DAY", count = 90) =>
    request<KLineResponse>(`/api/positions/kline/${encodeURIComponent(code)}?account_id=${encodeURIComponent(accountId)}&ktype=${encodeURIComponent(ktype)}&count=${count}`),
  generateAIAnalysis: (code: string, consentExternalAi = false, accountId = "all", model?: string, systemPrompt?: string) =>
    request<{ ai_analysis: AIAnalysis }>(`/api/positions/${encodeURIComponent(code)}/ai-analysis?account_id=${encodeURIComponent(accountId)}`, {
      method: "POST",
      body: JSON.stringify({ consent_external_ai: consentExternalAi, model, system_prompt: systemPrompt }),
    }),
  importPreview: (source: string, file: File, accountId = "") => {
    const form = new FormData();
    form.append("file", file);
    const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
    return request<ImportPreview>(`/api/import/${encodeURIComponent(source)}/preview${query}`, { method: "POST", body: form });
  },
  importConfirm: (source: string, preview: ImportPreview) =>
    request<{ sync_id: string; status: string; inserted_count: number; updated_count: number; error_message?: string }>(`/api/import/${encodeURIComponent(source)}/confirm`, {
      method: "POST",
      body: JSON.stringify(preview),
    }),
  downloadImportTemplate: (context: "position" | "deal" = "position") => downloadFile(`/api/import/excel/template?context=${context}`, `ai-portfolio-${context}-template.xlsx`),
  manualSync: () => request<{ sync_id: string; status: string; message: string }>("/api/sync/manual", { method: "POST" }),
  generateDecisionCards: (consentExternalAi = false, model?: string, systemPrompt?: string) =>
    request<{ status: string; model?: string; prompt_hash?: string; generated_count: number; failed: Array<{ code: string; error: string }> }>("/api/decision-cards/generate-ai", {
      method: "POST",
      body: JSON.stringify({ consent_external_ai: consentExternalAi, model, system_prompt: systemPrompt }),
    }),
  updateLayer: (code: string, position_layer: string, reason = "") =>
    request(`/api/positions/${encodeURIComponent(code)}/layer`, {
      method: "PATCH",
      body: JSON.stringify({ position_layer, reason }),
    }),
  deleteLocalData: () =>
    request<{ status: string }>("/api/data/delete-local", {
      method: "POST",
      body: JSON.stringify({ confirmation: "DELETE_LOCAL_DATA" }),
    }),
};
