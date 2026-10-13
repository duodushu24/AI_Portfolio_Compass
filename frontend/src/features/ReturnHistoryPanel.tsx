import { useState } from "react";
import { Button, Drawer, Table } from "@arco-design/web-react";
import { api, AccountSummary, ReturnPoint, HoldingHistoryItem } from "../api";
import { PortfolioPanel, timeLabel } from "./portfolio/PortfolioPanel";

// Old observations remain readable source material; the account ledger owns new writes.
export function ReturnHistoryPanel({ selectedAccount, accounts: _accounts, maskAssets, onChanged: _onChanged, onOpen }: { selectedAccount: string; accounts: AccountSummary[]; maskAssets: boolean; onChanged: () => Promise<void>; onOpen?: (code: string) => void }) {
  const [legacy, setLegacy] = useState<{ points: ReturnPoint[]; holdings: HoldingHistoryItem[] } | null>(null), [error, setError] = useState("");
  async function readLegacy() {
    try { const [series, holdings] = await Promise.all([api.returnSeries(selectedAccount, "CNY"), api.holdingHistory(selectedAccount, "")]); setLegacy({ points: series.items, holdings: holdings.items }); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "读取失败"); }
  }
  return <div className="stack"><PortfolioPanel accountId={selectedAccount} maskAssets={maskAssets} onOpen={onOpen} showPositions={false} /><div><Button onClick={readLegacy}>查看建档前来源记录</Button>{error && <p>{error}</p>}</div>
    {legacy && <Drawer visible title="原持仓快照与旧收益观察（来源记录）" width={1000} footer={null} onCancel={() => setLegacy(null)}><p>这些资料继续保留，不是新账目的成交、清仓利润或完整账户净值。新增业务到账户与数据记账。</p>
      <Table rowKey="id" data={legacy.holdings} pagination={{ pageSize: 8 }} columns={[{ title: "实际时间", dataIndex: "snapshot_time", render: timeLabel }, { title: "账户 / 标的", render: (_, r) => `${r.account_id} · ${r.code}` }, { title: "原数量 / 均价", render: (_, r) => maskAssets ? "••••" : `${r.quantity} / ${r.average_cost} ${r.raw_currency}` }]} />
      <Table rowKey="id" data={legacy.points} pagination={{ pageSize: 8 }} columns={[{ title: "旧观察时间", dataIndex: "observed_at", render: timeLabel }, { title: "说明", render: () => "旧持仓收益观察，不含完整现金/资金流" }]} />
    </Drawer>}
  </div>;
}
