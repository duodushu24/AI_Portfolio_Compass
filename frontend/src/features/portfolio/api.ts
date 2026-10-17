import { request } from "../../api";
import type { ClosedQuery, HistoryPreview, Opening, Portfolio, Reconciliation } from "./types";
const write = (method: string, payload: unknown) => ({ method, body: JSON.stringify(payload) });
export const portfolioApi = {
  closed: (filters: Record<string, string>) => request<ClosedQuery>(`/api/portfolio/closed?${new URLSearchParams(filters)}`),
  overview: (accountId = "all", code = "", at = "") => request<Portfolio>(`/api/portfolio/overview?${new URLSearchParams({ account_id: accountId, ...(code ? { code } : {}), ...(at ? { at } : {}) })}`),
  opening: (accountId: string) => request<{ confirmed: boolean; opening: Opening; reconciliation: Reconciliation[] }>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/opening`),
  saveOpening: (accountId: string, data: unknown, correction: boolean) => request<Portfolio>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/opening?correction=${correction}`, write("PUT", data)),
  saveTrade: (data: unknown, id?: number) => request<{ id: number }>(`/api/portfolio/trades${id ? `/${id}` : ""}`, write(id ? "PUT" : "POST", data)),
  previewHistory: (accountId: string, data: unknown) => request<HistoryPreview>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/history/preview`, write("POST", data)),
  saveHistory: (accountId: string, data: unknown) => request<HistoryPreview>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/history`, write("POST", data)),
  saveEvent: (data: unknown, id?: number) => request<{ id: number }>(`/api/portfolio/events${id ? `/${id}` : ""}`, write(id ? "PUT" : "POST", data)),
  void: (category: string, id: number) => request(`/api/portfolio/${category === "trade" ? "trades" : "events"}/${id}`, { method: "DELETE" }),
};
