import { useState, useEffect, useMemo, memo, useCallback } from 'react'
import { TrendingUp, TrendingDown, Zap, Calculator, AlertTriangle, Save, ArrowRight, ArrowLeft, RefreshCw } from 'lucide-react'
import type { FundingRate } from '../types'

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

const ResultCard = memo(({ label, val, color, bold }: { label: string; val: number; color: string; bold?: boolean }) => (
  <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
    <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">{label}</div>
    <div className={`text-sm ${bold ? 'font-black' : 'font-bold'} ${color}`}>{val >= 0 ? '+' : ''}${val.toFixed(2)}</div>
  </div>
))

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

  // Auto-fill when symbol+exchange changes
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
      [side === 'A' ? 'entryA' : 'entryB']: mp,
      [side === 'A' ? 'exitA' : 'exitB']: mp,
      [side === 'A' ? 'rateA' : 'rateB']: rate,
    }))
  }, [i.symbol, rates])

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
            <div className="min-w-[200px]">
              <Selector label="Trading Pair" options={symbols} value={i.symbol}
                onChange={v => setI(p => ({ ...p, symbol: v, nameA: '', nameB: '', entryA: 0, exitA: 0, entryB: 0, exitB: 0, rateA: 0, rateB: 0 }))} />
            </div>
            <div className="text-[9px] text-gray-600 flex items-center gap-2 pb-1">
              <RefreshCw size={12} className="text-blue-500" /> {Object.keys(rates).length} live rates
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Exchange A — Long */}
            <div className="bg-[#0a0a0a] border border-green-900/30 rounded-2xl p-5">
              <div className="text-[10px] font-black text-green-500 uppercase tracking-widest mb-4 flex items-center gap-2"><TrendingUp size={12} /> Long Leg</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Exchange</label>
                  <select value={i.nameA} onChange={e => { setStr('nameA')(e.target.value); autoFill('A', e.target.value) }}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-green-600 transition-colors appearance-none cursor-pointer">
                    <option value="">---</option>
                    {exOptionsA.map(ex => <option key={ex} value={ex}>{ex}</option>)}
                  </select>
                </div>
                <NumInput label="Funding Rate %" val={i.rateA} onChange={setNum('rateA')} />
                <NumInput label="Entry Price" val={i.entryA} onChange={setNum('entryA')} />
                <NumInput label="Exit Price" val={i.exitA} onChange={setNum('exitA')} />
                <NumInput label="Taker Fee %" val={i.feeA} onChange={setNum('feeA')} />
              </div>
            </div>

            {/* Exchange B — Short */}
            <div className="bg-[#0a0a0a] border border-red-900/30 rounded-2xl p-5">
              <div className="text-[10px] font-black text-red-500 uppercase tracking-widest mb-4 flex items-center gap-2"><TrendingDown size={12} /> Short Leg</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Exchange</label>
                  <select value={i.nameB} onChange={e => { setStr('nameB')(e.target.value); autoFill('B', e.target.value) }}
                    className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-red-600 transition-colors appearance-none cursor-pointer">
                    <option value="">---</option>
                    {exOptionsB.map(ex => <option key={ex} value={ex}>{ex}</option>)}
                  </select>
                </div>
                <NumInput label="Funding Rate %" val={i.rateB} onChange={setNum('rateB')} />
                <NumInput label="Entry Price" val={i.entryB} onChange={setNum('entryB')} />
                <NumInput label="Exit Price" val={i.exitB} onChange={setNum('exitB')} />
                <NumInput label="Taker Fee %" val={i.feeB} onChange={setNum('feeB')} />
              </div>
            </div>
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
  )
}
