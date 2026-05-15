import { useState, useEffect, useMemo, memo, useCallback, useRef } from 'react'
import { TrendingUp, TrendingDown, Zap, Calculator, AlertTriangle, Save, ArrowRight, ArrowLeft, RefreshCw, ArrowUpDown, Search, BookOpen } from 'lucide-react'
import type { FundingRate } from '../types'
const fmtPrice = (p: number) => {
  if (!p) return '0'
  if (p >= 10000) return p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (p >= 100) return p.toFixed(4)
  if (p >= 1) return p.toFixed(6)
  if (p >= 0.01) return p.toFixed(8)
  return p.toFixed(10)
}
const fmtQty = (n: number) => n >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : n.toFixed(4)

interface CalcInputs {
  symbol: string
  nameA: string; entryA: number; exitA: number; feeA: number; rateA: number
  nameB: string; entryB: number; exitB: number; feeB: number; rateB: number
  size: number; leverage: number; cycles: number
}

interface CalcResults {
  notional: number; fundingIncome: number; pricePnl: number; totalFees: number; spreadCost: number
  netProfit: number; roi: number; isProfitable: boolean; breakEvenRate: number
}

const STORAGE_KEY = 'quantmatrix_calc3'
const DEFAULTS: CalcInputs = {
  symbol: '', nameA: '', entryA: 0, exitA: 0, feeA: 0.06, rateA: 0,
  nameB: '', entryB: 0, exitB: 0, feeB: 0.06, rateB: 0,
  size: 1, leverage: 1, cycles: 1,
}

function loadSaved(): CalcInputs {
  try { const s = localStorage.getItem(STORAGE_KEY); if (s) return { ...DEFAULTS, ...JSON.parse(s) } } catch {}
  return DEFAULTS
}

function calc(i: CalcInputs): CalcResults {
  const n = i.size * i.entryA * i.leverage
  const fi = n * (i.rateB - i.rateA) / 100 * i.cycles
  const pl = ((i.exitA - i.entryA) - (i.exitB - i.entryB)) * i.size * i.leverage
  const tf = n * (i.feeA + i.feeB) / 100 * 2
  const sc = Math.abs(i.entryA - i.entryB) * i.size * i.leverage + Math.abs(i.exitA - i.exitB) * i.size * i.leverage
  const np = fi + pl - tf - sc
  const roi = n > 0 ? (np / n) * 100 : 0
  return { notional: n, fundingIncome: fi, pricePnl: pl, totalFees: tf, spreadCost: sc, netProfit: np, roi, isProfitable: np > 0, breakEvenRate: n > 0 ? (tf + sc) / n * 100 / i.cycles : 0 }
}

const NumInput = memo(({ label, val, onChange }: { label: string; val: number | string; onChange: (v: string) => void }) => (
  <div>
    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">{label}</label>
    <input type="number" step="any" value={val} onChange={e => onChange(e.target.value)}
      className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
  </div>
))

const Selector = memo(({ label, options, value, onChange }: { label: string; options: string[]; value: string; onChange: (v: string) => void }) => (
  <div>
    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">{label}</label>
    <select value={value} onChange={e => onChange(e.target.value)}
      className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors appearance-none cursor-pointer">
      <option value="">---</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  </div>
))

const SymbolPicker = memo(({ symbols, value, onChange }: { symbols: string[]; value: string; onChange: (v: string) => void }) => {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = useMemo(() => {
    if (!query) return symbols
    const q = query.toLowerCase()
    return symbols.filter(s => s.toLowerCase().includes(q))
  }, [symbols, query])

  return (
    <div ref={ref} className="relative">
      <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Trading Pair</label>
      <div className="relative">
        <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 pointer-events-none" />
        <input type="text" value={open ? query : value} placeholder="Search pair..." onFocus={() => { setOpen(true); setQuery('') }}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          className="w-full bg-[#111] border border-gray-800 rounded-xl pl-8 pr-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
      </div>
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 bg-[#111] border border-gray-800 rounded-xl max-h-48 overflow-y-auto z-10 custom-scrollbar">
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-[10px] text-gray-600">No matches</div>
          ) : filtered.slice(0, 50).map(s => (
            <button key={s} onClick={() => { onChange(s); setOpen(false); setQuery(s) }}
              className={`w-full text-left px-3 py-2 text-xs font-bold transition-colors ${s === value ? 'text-purple-500 bg-purple-500/10' : 'text-white hover:bg-white/5'}`}>
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
})

const ResultCard = memo(({ label, val, color, bold }: { label: string; val: number; color: string; bold?: boolean }) => (
  <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
    <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">{label}</div>
    <div className={`text-sm ${bold ? 'font-black' : 'font-bold'} ${color}`}>{val >= 0 ? '+' : ''}${val.toFixed(2)}</div>
  </div>
))

const DepthSection = memo(({ exchange, symbol }: { exchange: string; symbol: string }) => {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [buySize, setBuySize] = useState(10000)
  const [maxSlippage, setMaxSlippage] = useState(0.1)
  const debounceRef = useRef<any>(null)

  // Debounced fetch: only when user stops typing for 400ms
  const fetchData = useCallback((qty: number) => {
    if (!open || !exchange || !symbol) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setLoading(true)
      fetch(`/api/orderbook/${exchange}/${symbol}?buy_size=${qty}&sell_size=${qty}`)
        .then(r => r.json()).then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false))
    }, 400)
  }, [open, exchange, symbol])

  useEffect(() => {
    fetchData(buySize)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [buySize])

  useEffect(() => {
    if (open && !data) fetchData(buySize)
  }, [open])

  // Calculate max order size for given max slippage
  const suggestedSize = useMemo(() => {
    if (!data?.asks || !data?.bids) return null
    const maxSlippageRatio = maxSlippage / 100
    const bestAsk = data.best_ask
    const bestBid = data.best_bid
    if (!bestAsk || !bestBid) return null

    // Walk through asks until slippage exceeds limit
    let buyQty = 0, buyCost = 0
    for (const [price, qty] of data.asks) {
      const nextBuyQty = buyQty + qty
      const nextBuyCost = buyCost + qty * price
      const avgPrice = nextBuyCost / nextBuyQty
      const slippage = (avgPrice - bestAsk) / bestAsk
      if (slippage > maxSlippageRatio) {
        // Interpolate: how much can we take within limit?
        const maxTake = (maxSlippageRatio * bestAsk * buyQty + buyCost - buyQty * bestAsk) / (bestAsk * (1 + maxSlippageRatio) - price)
        buyQty += Math.max(0, maxTake)
        break
      }
      buyQty = nextBuyQty
      buyCost = nextBuyCost
    }

    // Same for sell side
    let sellQty = 0, sellValue = 0
    for (const [price, qty] of data.bids) {
      const nextSellQty = sellQty + qty
      const nextSellValue = sellValue + qty * price
      const avgPrice = nextSellValue / nextSellQty
      const slippage = (bestBid - avgPrice) / bestBid
      if (slippage > maxSlippageRatio) {
        const maxTake = (buyQty * bestBid - bestBid * (1 - maxSlippageRatio) * buyQty - buyCost + bestBid * buyQty) / (bestBid - price)
        sellQty += Math.max(0, maxTake)
        break
      }
      sellQty = nextSellQty
      sellValue = nextSellValue
    }

    return { buy: Math.round(buyQty), sell: Math.round(sellQty) }
  }, [data, maxSlippage])

  if (!exchange) return null

  return (
    <div className="mt-2">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-[8px] font-bold text-gray-600 uppercase tracking-wider hover:text-gray-400 transition-colors">
        <BookOpen size={10} /> Depth & Liquidity {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="mt-2 bg-[#111] rounded-xl p-3 border border-gray-800">
          {loading && !data ? (
            <div className="text-[8px] text-gray-600 animate-pulse">Loading order book...</div>
          ) : data?.error ? (
            <div className="text-[8px] text-red-500">{data.error}</div>
          ) : data ? (
            <>
              <div className="grid grid-cols-2 gap-2 mb-2 text-[8px]">
                <div><span className="text-gray-600">Bid:</span> <span className="text-green-500 font-bold">${fmtPrice(data.best_bid)}</span></div>
                <div><span className="text-gray-600">Ask:</span> <span className="text-red-500 font-bold">${fmtPrice(data.best_ask)}</span></div>
                <div><span className="text-gray-600">Spread:</span> <span className="text-white font-bold">{data.spread_pct}%</span></div>
                <div><span className="text-gray-600">Depth:</span> <span className="text-white font-bold">{data.bid_depth}/{data.ask_depth}</span></div>
              </div>

              <div className="flex items-center gap-2 mb-2">
                <span className="text-[7px] text-gray-600 whitespace-nowrap">Qty:</span>
                <input type="number" value={buySize} onChange={e => { const v = parseFloat(e.target.value); if (!isNaN(v)) setBuySize(v) }}
                  className="w-20 bg-black border border-gray-800 rounded-lg px-2 py-1 text-[8px] font-bold text-white focus:outline-none" />
                {loading && <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />}
              </div>

              <div className="grid grid-cols-2 gap-2 mb-3 text-[8px]">
                <div>
                  <div className="text-gray-600 mb-1">Buy {buySize.toLocaleString()}</div>
                  <div className="text-green-500 font-bold">~${fmtPrice(data.buy_analysis?.avg_price)}</div>
                  <div className="text-gray-700">slippage: {data.buy_analysis?.slippage_pct}% (${data.buy_analysis?.slippage_cost})</div>
                  {data.buy_analysis?.remaining > 0 && <div className="text-yellow-600">{fmtQty(data.buy_analysis.remaining)} unfilled</div>}
                </div>
                <div>
                  <div className="text-gray-600 mb-1">Sell {buySize.toLocaleString()}</div>
                  <div className="text-red-500 font-bold">~${fmtPrice(data.sell_analysis?.avg_price)}</div>
                  <div className="text-gray-700">slippage: {data.sell_analysis?.slippage_pct}% (${data.sell_analysis?.slippage_cost})</div>
                  {data.sell_analysis?.remaining > 0 && <div className="text-yellow-600">{data.sell_analysis.remaining} unfilled</div>}
                </div>
              </div>

              <div className="border-t border-gray-800 pt-2">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[7px] text-gray-600 whitespace-nowrap">Max slippage:</span>
                  <input type="number" step="0.01" value={maxSlippage} onChange={e => { const v = parseFloat(e.target.value); if (!isNaN(v)) setMaxSlippage(v) }}
                    className="w-14 bg-black border border-gray-800 rounded-lg px-2 py-1 text-[8px] font-bold text-white focus:outline-none" />
                  <span className="text-[7px] text-gray-600">%</span>
                </div>
                {suggestedSize && (
                  <div className="grid grid-cols-2 gap-2 text-[8px]">
                    <div><span className="text-gray-600">Max buy:</span> <span className="text-green-500 font-bold">{suggestedSize.buy.toLocaleString()}</span></div>
                    <div><span className="text-gray-600">Max sell:</span> <span className="text-red-500 font-bold">{suggestedSize.sell.toLocaleString()}</span></div>
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  )
})

interface Props { rates: Record<string, FundingRate> }

export function ArbitrageCalculator({ rates }: Props) {
  const saved = useMemo(() => loadSaved(), [])
  const [i, setI] = useState<CalcInputs>(saved)
  const [savedIcon, setSavedIcon] = useState(false)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(i))
    setSavedIcon(true); const t = setTimeout(() => setSavedIcon(false), 2000); return () => clearTimeout(t)
  }, [i])

  // Build symbol / exchange index from rates
  const { symbols, exForSym } = useMemo(() => {
    const symSet = new Set<string>(), exMap: Record<string, string[]> = {}
    for (const key of Object.keys(rates)) {
      const r = rates[key]
      if (!r.symbol) continue
      symSet.add(r.symbol)
      if (!exMap[r.symbol]) exMap[r.symbol] = []
      if (!exMap[r.symbol].includes(r.exchange)) exMap[r.symbol].push(r.exchange)
    }
    const sorted = [...symSet].sort()
    return { symbols: sorted, exForSym: exMap }
  }, [rates])

  const setNum = useCallback((k: keyof CalcInputs) => (v: string) => {
    const n = parseFloat(v); if (!isNaN(n)) setI(p => ({ ...p, [k]: n }))
  }, [])

  const setStr = useCallback((k: keyof CalcInputs) => (v: string) => setI(p => ({ ...p, [k]: v })), [])

  // Get market data for an exchange+symbol
  const marketFor = useCallback((side: 'A' | 'B') => {
    const ex = side === 'A' ? i.nameA : i.nameB
    if (!i.symbol || !ex) return null
    const key = `${ex}:${i.symbol}`
    const r = rates[key]
    if (!r) return null
    return { markPrice: r.mark_price ?? 0, fundingRate: r.rate * 100 }
  }, [i.symbol, i.nameA, i.nameB, rates])

  const applyEntry = useCallback((side: 'A' | 'B') => {
    const m = marketFor(side)
    if (!m) return
    setI(p => ({ ...p, [side === 'A' ? 'entryA' : 'entryB']: m.markPrice }))
  }, [marketFor])

  const applyExit = useCallback((side: 'A' | 'B') => {
    const m = marketFor(side)
    if (!m) return
    setI(p => ({ ...p, [side === 'A' ? 'exitA' : 'exitB']: m.markPrice }))
  }, [marketFor])

  const autoFill = useCallback((side: 'A' | 'B', ex: string) => {
    if (!i.symbol || !ex) return
    const key = `${ex}:${i.symbol}`
    const r = rates[key]
    if (!r) return
    const mp = r.mark_price ?? 0
    const rate = r.rate * 100
    setI(p => ({
      ...p,
      [side === 'A' ? 'nameA' : 'nameB']: ex,
      [side === 'A' ? 'exitA' : 'exitB']: mp,
      [side === 'A' ? 'rateA' : 'rateB']: rate,
    }))
  }, [i.symbol, rates])

  const swapLegs = useCallback(() => {
    setI(p => ({
      ...p,
      nameA: p.nameB, entryA: p.entryB, exitA: p.exitB, feeA: p.feeB, rateA: p.rateB,
      nameB: p.nameA, entryB: p.entryA, exitB: p.exitA, feeB: p.feeA, rateB: p.rateA,
    }))
  }, [])

  const r = calc(i)
  const profit = r.isProfitable
  const netC = profit ? 'text-green-500' : 'text-red-500'
  const netBg = profit ? 'bg-green-500/10 border-green-900/30' : 'bg-red-500/10 border-red-900/30'

  const exOptionsA = i.symbol ? exForSym[i.symbol] || [] : []
  const exOptionsB = i.symbol ? exForSym[i.symbol] || [] : []

  return (
    <div className="w-full">
      <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl overflow-hidden">
        <div className="h-1 bg-gradient-to-r from-blue-600 via-purple-500 to-pink-500" />
        <div className="flex items-center justify-between px-8 py-5 border-b border-gray-900">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/10 rounded-xl"><Calculator size={18} className="text-purple-500" /></div>
            <div>
              <h2 className="text-lg font-black text-white uppercase tracking-tight">Arbitrage Calculator</h2>
              <p className="text-[9px] font-bold text-gray-600 uppercase tracking-widest mt-0.5">Cross-Exchange Funding Rate Arbitrage</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => setI(DEFAULTS)} className="text-[9px] font-black uppercase bg-[#111] px-4 py-2 rounded-xl border border-gray-800 text-gray-500 hover:text-white transition-all">Reset</button>
            <div className={`flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-wider transition-all duration-300 ${savedIcon ? 'opacity-100' : 'opacity-0'}`}>
              <Save size={10} className="text-green-500" /> <span className="text-green-500">Saved</span>
            </div>
          </div>
        </div>

        <div className="p-8">
          {/* Symbol selector */}
          <div className="flex gap-4 mb-6 bg-[#0a0a0a] border border-gray-800 rounded-2xl p-4 items-end">
            <div className="min-w-[220px]">
              <SymbolPicker symbols={symbols} value={i.symbol}
                onChange={v => setI(p => ({ ...p, symbol: v, nameA: '', nameB: '', entryA: 0, exitA: 0, entryB: 0, exitB: 0, rateA: 0, rateB: 0 }))} />
            </div>
            <div className="text-[9px] text-gray-600 flex items-center gap-2 pb-1">
              <RefreshCw size={12} className="text-blue-500" /> {Object.keys(rates).length} live rates
            </div>
          </div>

          <div className="relative grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Swap button */}
            <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 hidden lg:block">
              <button onClick={swapLegs} className="p-2 rounded-xl bg-[#111] border border-gray-800 text-gray-500 hover:text-purple-500 hover:border-purple-600 transition-all" title="Swap Long/Short">
                <ArrowUpDown size={16} />
              </button>
            </div>

            {/* Exchange A — Long */}
            <div className="bg-[#0a0a0a] border border-green-900/30 rounded-2xl p-5">
              <div className="text-[10px] font-black text-green-500 uppercase tracking-widest mb-4 flex items-center gap-2"><TrendingUp size={12} /> Long Leg</div>
              {(() => { const m = marketFor('A'); return m ? (
                <div className="text-[8px] text-gray-600 mb-3 flex items-center gap-3 bg-green-900/10 rounded-lg px-3 py-2">
                  <span>Market: <span className="text-white font-bold">${fmtPrice(m.markPrice)}</span></span>
                  <span>Rate: <span className={m.fundingRate >= 0 ? 'text-green-500' : 'text-red-500'}>{m.fundingRate >= 0 ? '+' : ''}{m.fundingRate.toFixed(4)}%</span></span>
                </div>
              ) : null})()}
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <div>
                  <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Exchange</label>
                  <select value={i.nameA} onChange={e => { setStr('nameA')(e.target.value); autoFill('A', e.target.value) }}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-green-600 transition-colors appearance-none cursor-pointer">
                    <option value="">---</option>
                    {exOptionsA.map(ex => <option key={ex} value={ex}>{ex}</option>)}
                  </select>
                </div>
                <NumInput label="Funding Rate %" val={i.rateA} onChange={setNum('rateA')} />
                <div className="relative">
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider">Entry Price</label>
                    {i.nameA && <button onClick={() => applyEntry('A')} className="text-[7px] font-bold text-green-600 hover:text-green-400 transition-colors border border-green-900/30 px-1.5 py-0.5 rounded" title="Apply current market price">Apply</button>}
                  </div>
                  <input type="number" step="any" value={i.entryA} onChange={e => setNum('entryA')(e.target.value)}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-green-600 transition-colors" />
                </div>
                <div className="relative">
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider">Exit Price</label>
                    {i.nameA && <button onClick={() => applyExit('A')} className="text-[7px] font-bold text-green-600 hover:text-green-400 transition-colors border border-green-900/30 px-1.5 py-0.5 rounded" title="Apply current market price">Apply</button>}
                  </div>
                  <input type="number" step="any" value={i.exitA} onChange={e => setNum('exitA')(e.target.value)}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-green-600 transition-colors" />
                </div>
                <NumInput label="Taker Fee %" val={i.feeA} onChange={setNum('feeA')} />
              </div>
              {i.entryA > 0 && i.exitA > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-800 flex justify-between items-center">
                  <span className="text-[8px] font-bold text-gray-600 uppercase tracking-wider">Long P&L</span>
                  <span className={`text-[11px] font-black ${(i.exitA - i.entryA) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {(i.exitA - i.entryA) >= 0 ? '+' : ''}${((i.exitA - i.entryA) * i.size * i.leverage).toFixed(2)}
                  </span>
                </div>
              )}
              <DepthSection exchange={i.nameA} symbol={i.symbol} />
            </div>

            {/* Swap button below on mobile */}
            <div className="flex justify-center lg:hidden">
              <button onClick={swapLegs} className="p-2 rounded-xl bg-[#111] border border-gray-800 text-gray-500 hover:text-purple-500 transition-all">
                <ArrowUpDown size={16} /> <span className="text-[10px] font-bold uppercase ml-1">Swap Legs</span>
              </button>
            </div>

            {/* Exchange B — Short */}
            <div className="bg-[#0a0a0a] border border-red-900/30 rounded-2xl p-5">
              <div className="text-[10px] font-black text-red-500 uppercase tracking-widest mb-4 flex items-center gap-2"><TrendingDown size={12} /> Short Leg</div>
              {(() => { const m = marketFor('B'); return m ? (
                <div className="text-[8px] text-gray-600 mb-3 flex items-center gap-3 bg-red-900/10 rounded-lg px-3 py-2">
                  <span>Market: <span className="text-white font-bold">${fmtPrice(m.markPrice)}</span></span>
                  <span>Rate: <span className={m.fundingRate >= 0 ? 'text-green-500' : 'text-red-500'}>{m.fundingRate >= 0 ? '+' : ''}{m.fundingRate.toFixed(4)}%</span></span>
                </div>
              ) : null})()}
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <div>
                  <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Exchange</label>
                  <select value={i.nameB} onChange={e => { setStr('nameB')(e.target.value); autoFill('B', e.target.value) }}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-red-600 transition-colors appearance-none cursor-pointer">
                    <option value="">---</option>
                    {exOptionsB.map(ex => <option key={ex} value={ex}>{ex}</option>)}
                  </select>
                </div>
                <NumInput label="Funding Rate %" val={i.rateB} onChange={setNum('rateB')} />
                <div className="relative">
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider">Entry Price</label>
                    {i.nameB && <button onClick={() => applyEntry('B')} className="text-[7px] font-bold text-red-600 hover:text-red-400 transition-colors border border-red-900/30 px-1.5 py-0.5 rounded" title="Apply current market price">Apply</button>}
                  </div>
                  <input type="number" step="any" value={i.entryB} onChange={e => setNum('entryB')(e.target.value)}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-red-600 transition-colors" />
                </div>
                <div className="relative">
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider">Exit Price</label>
                    {i.nameB && <button onClick={() => applyExit('B')} className="text-[7px] font-bold text-red-600 hover:text-red-400 transition-colors border border-red-900/30 px-1.5 py-0.5 rounded" title="Apply current market price">Apply</button>}
                  </div>
                  <input type="number" step="any" value={i.exitB} onChange={e => setNum('exitB')(e.target.value)}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-red-600 transition-colors" />
                </div>
                <NumInput label="Taker Fee %" val={i.feeB} onChange={setNum('feeB')} />
              </div>
              {i.entryB > 0 && i.exitB > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-800 flex justify-between items-center">
                  <span className="text-[8px] font-bold text-gray-600 uppercase tracking-wider">Short P&L</span>
                  <span className={`text-[11px] font-black ${(i.entryB - i.exitB) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {(i.entryB - i.exitB) >= 0 ? '+' : ''}${((i.entryB - i.exitB) * i.size * i.leverage).toFixed(2)}
                  </span>
                </div>
              )}
              <DepthSection exchange={i.nameB} symbol={i.symbol} />
          </div>

          <div className="flex flex-wrap gap-4 mb-8 bg-[#0a0a0a] border border-gray-800 rounded-2xl p-5 items-end">
            <div className="flex items-center gap-2 text-[10px] font-black text-gray-600 uppercase tracking-widest mr-2 mb-1"><Zap size={12} /> Position</div>
            <NumInput label="Size (units)" val={i.size} onChange={setNum('size')} />
            <NumInput label="Leverage" val={i.leverage} onChange={setNum('leverage')} />
            <NumInput label="Funding Cycles" val={i.cycles} onChange={setNum('cycles')} />
            <div className="flex items-center bg-[#111] rounded-xl px-4 border border-gray-800 h-[42px]">
              <span className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mr-2">Notional</span>
              <span className="text-xs font-black text-white">{r.notional.toLocaleString()}</span>
            </div>
          </div>

          <div className={`rounded-2xl border p-6 ${netBg}`}>
            <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-5">P&L Breakdown</div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
              <ResultCard label="Funding Income" val={r.fundingIncome} color={r.fundingIncome >= 0 ? 'text-green-500' : 'text-red-500'} />
              <ResultCard label="Price P&L" val={r.pricePnl} color={r.pricePnl >= 0 ? 'text-green-500' : 'text-red-500'} />
              <ResultCard label="Spread Cost" val={-r.spreadCost} color="text-yellow-500" />
              <ResultCard label="Trading Fees" val={-r.totalFees} color="text-red-500" />
              <ResultCard label="Net Profit" val={r.netProfit} color={netC} bold />
            </div>
            <div className="flex flex-wrap items-center gap-6">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-xl ${profit ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                  {profit ? <TrendingUp size={20} className="text-green-500" /> : <TrendingDown size={20} className="text-red-500" />}
                </div>
                <div>
                  <div className={`text-2xl font-black ${netC}`}>{r.netProfit >= 0 ? '+' : ''}{r.netProfit.toFixed(2)} USDT</div>
                  <div className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mt-0.5">
                    ROI: <span className={netC}>{r.roi >= 0 ? '+' : ''}{r.roi.toFixed(4)}%</span>
                    &nbsp;·&nbsp;Break-even: <span className="text-white">{r.breakEvenRate.toFixed(4)}%</span>/cycle
                  </div>
                </div>
              </div>
              {r.pricePnl !== 0 && <div className="h-10 w-px bg-gray-800" />}
              {r.pricePnl !== 0 && (
                <div className="text-[9px] text-gray-500 font-bold leading-relaxed">
                  <div className="flex items-center gap-1"><ArrowRight size={10} /> {i.nameA}: ${i.entryA.toFixed(2)} → ${i.exitA.toFixed(2)}</div>
                  <div className="flex items-center gap-1"><ArrowLeft size={10} /> {i.nameB}: ${i.entryB.toFixed(2)} → ${i.exitB.toFixed(2)}</div>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 flex items-start gap-3 bg-[#0a0a0a] border border-gray-800 rounded-2xl p-4">
            <AlertTriangle size={14} className="text-yellow-500 shrink-0 mt-0.5" />
            <div className="text-[9px] text-gray-600 leading-relaxed">
              <span className="font-bold text-gray-500">Strategy:</span> Long low-rate leg + Short high-rate leg. Positive rate → Longs pay Shorts.
              Select a trading pair, then choose exchanges to auto-fill live prices &amp; funding rates.
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>
  )
}
