import { request } from "../../api";
import type { ChartPoint, ClosedQuery, HistoryPreview, Opening, Point, Portfolio, Reconciliation } from "./types";
const write = (method: string, payload: unknown) => ({ method, body: JSON.stringify(payload) });
export const portfolioApi = {
  point: (accountId: string, point: ChartPoint, code = "") => request<Point>(`/api/portfolio/point?${new URLSearchParams({ account_id: accountId, at: point.observed_at, event_type: point.event_type, owner_id: point.account_id, ...(point.record_id == null ? {} : { record_id: String(point.record_id) }), ...(code ? { code } : {}) })}`),
  closed: (filters: Record<string, string>) => request<ClosedQuery>(`/api/portfolio/closed?${new URLSearchParams(filters)}`),
  overview: (accountId = "all", code = "", at = "", view = "chart") => request<Portfolio>(`/api/portfolio/overview?${new URLSearchParams({ account_id: accountId, view, ...(code ? { code } : {}), ...(at ? { at } : {}) })}`),
  opening: (accountId: string) => request<{ confirmed: boolean; opening: Opening; reconciliation: Reconciliation[] }>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/opening`),
  saveOpening: (accountId: string, data: unknown, correction: boolean) => request<Portfolio>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/opening?correction=${correction}`, write("PUT", data)),
  saveTrade: (data: unknown, id?: number) => request<{ id: number }>(`/api/portfolio/trades${id ? `/${id}` : ""}`, write(id ? "PUT" : "POST", data)),
  previewHistory: (accountId: string, data: unknown) => request<HistoryPreview>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/history/preview`, write("POST", data)),
  saveHistory: (accountId: string, data: unknown) => request<HistoryPreview>(`/api/portfolio/accounts/${encodeURIComponent(accountId)}/history`, write("POST", data)),
  saveEvent: (data: unknown, id?: number) => request<{ id: number }>(`/api/portfolio/events${id ? `/${id}` : ""}`, write(id ? "PUT" : "POST", data)),
  void: (category: string, id: number) => request(`/api/portfolio/${category === "trade" ? "trades" : "events"}/${id}`, { method: "DELETE" }),
};
