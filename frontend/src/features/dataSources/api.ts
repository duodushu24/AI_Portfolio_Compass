import { request } from "../../api";
export const OPEN_DATA_SOURCES = "portfolio-open-data-sources";

export type SourceCheck = {status: string; message: string; checked_at?: string; sample_count?: number};
export type ProviderItem = {id: string; label: string; group: "free" | "paid"; description: string;
  capabilities: string[]; markets: string[]; fields: Array<{key: string; label: string; type: string; default?: unknown}>;
  config: Record<string, string | number | boolean | null>; secrets: Record<string, boolean>;
  status: string; message: string; last_check: SourceCheck | null};
export const sourceApi = {
  list: () => request<{items: ProviderItem[]}>("/api/data-sources"),
  save: (id: string, data: unknown) => request<{items: ProviderItem[]}>(`/api/data-sources/${encodeURIComponent(id)}`, {method: "PUT", body: JSON.stringify(data)}),
  check: (id: string, dataType: string) => request<SourceCheck>(`/api/data-sources/${encodeURIComponent(id)}/check`, {method: "POST", body: JSON.stringify({data_type: dataType})}),
};
