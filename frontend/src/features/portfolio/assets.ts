export const assetOptions = [
  { value: "stock", label: "股票" }, { value: "etf", label: "场内基金 / ETF" },
  { value: "fund", label: "场外基金" }, { value: "bond", label: "债券" },
  { value: "leveraged_etf", label: "杠杆 ETF" }, { value: "precious_metal", label: "贵金属（银行黄金）" },
];
export const assetUnit = (type: string) => type === "precious_metal" ? "gram" : type === "fund" ? "fund_unit" : "share";
export const unitLabel = (unit: string) => ({ gram: "克", fund_unit: "份", share: "股 / 份" }[unit] || unit);
export const priceUnit = (currency: string, unit: string) => `${({ CNY: "元", HKD: "港元", USD: "美元" }[currency] || currency)}/${unitLabel(unit)}`;
export const goldCode = () => `CN.GOLD.${crypto.randomUUID().replace(/-/g, "").toUpperCase()}`;
export const quoteKindLabel = (kind: string) => ({ redemption: "银行赎回 / 回购价", bank_value: "银行展示市值", nav: "正式净值", estimate: "估算", price: "价格" }[kind] || kind);
