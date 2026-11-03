export type AssetClass = 'AC' | 'FII' | 'RF' | 'BDR' | 'ETF' | 'INT';

export interface Position {
  name: string;
  asset_class: AssetClass;
  category: string | null;
  sub_category: string | null;
  volume: number;
  cost: number;
  price: number | null;
  value: number | null;
  profit: number | null;
  profit_pct: number | null;
  income: number;
  total_return: number | null;
  total_return_pct: number | null;
  description: string | null;
  issuer: string | null;
  index: string | null;
  maturity_date: string | null;
  brokers: { broker: string; volume: number }[];
  cost_estimated: boolean;
  estimated_rate: number | null;
  maturity_value: number | null;
  value_estimated: boolean;
}

export interface PositionSummary {
  value: number;
  invested: number;
  profit: number;
  profit_pct: number | null;
  assets: number;
  assets_without_price: number;
  estimated_assets: number;
  income_total: number;
  realized_gain: number;
  fixed_income_as_of: string | null;
}

export interface PerformanceSeries {
  dates: string[];
  portfolio: number[];
  cdi: (number | null)[];
  ibov: (number | null)[];
  ignored_days: number;
}

export interface PositionResponse {
  assets: Position[];
  summary: PositionSummary;
}

export interface PositionHistory {
  labels: string[];
  values: number[];
  invested: number[];
}

export interface Order {
  id: number;
  name: string;
  broker: string;
  asset_type: AssetClass;
  order_type: 1 | -1;
  date: string;
  price: number;
  volume: number;
  total: number;
  description: string | null;
  interest_rate: number | null;
  maturity_date: string | null;
  index: string | null;
  fixed_income_type: string | null;
  issuer: string | null;
  cost_estimated: boolean;
  source: 'manual' | 'position' | 'movement';
  kind: 'trade' | 'event' | 'transfer' | 'fraction' | 'succession' | 'reconcile';
  note: string;
}

export interface IncomeRow {
  date: string;
  name: string;
  description: string;
  asset_class: AssetClass;
  type: string;
  value: number;
}

export interface IncomeResponse {
  rows: IncomeRow[];
  costs: Record<string, number>;
}

export interface AssetInfo {
  ticker: string;
  asset_class: string | null;
  trading_name: string | null;
  company_name: string | null;
  category: string | null;
  sub_category: string | null;
}

export interface User {
  id: number;
  username: string;
  email: string;
  name?: string;
}
