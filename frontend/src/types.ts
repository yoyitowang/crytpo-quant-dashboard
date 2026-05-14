export interface FundingRate {
  exchange: string
  symbol: string
  rate: number
  mark_price?: number
  interval?: number
  settlement_time?: string
  timestamp: string
}

export interface AlertRule {
  id: string
  symbol: string
  exchange: string
  direction: 'above' | 'below'
  threshold: number
  enabled: boolean
  lastTriggeredAt: number | null
}

export interface AlertEvent {
  id: string
  ruleId: string
  symbol: string
  exchange: string
  rate: number
  message: string
  timestamp: number
}

export const EXCHANGE_COLORS: Record<string, string> = {
  binance: '#F3BA2F', okx: '#FFFFFF', bybit: '#FFB11A', bitget: '#00F0FF',
  gate: '#E02A44', kucoin: '#24AE8F', coinw: '#3B82F6', mexc: '#0081FF', bingx: '#3182CE', aden: '#6366F1',
}

export const ALL_EXCHANGES = ['binance', 'okx', 'bybit', 'bitget', 'gate', 'kucoin', 'coinw', 'mexc', 'bingx', 'aden']
