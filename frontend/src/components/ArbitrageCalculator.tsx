import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Zap, DollarSign, Calculator, AlertTriangle, Save, ArrowRight, ArrowLeft } from 'lucide-react'

interface CalcInputs {
  nameA: string; entryA: number; exitA: number; feeA: number; rateA: number
  nameB: string; entryB: number; exitB: number; feeB: number; rateB: number
  size: number; leverage: number; cycles: number
}

interface CalcResults {
  notional: number; fundingIncome: number; pricePnl: number; totalFees: number; spreadCost: number
  netProfit: number; roi: number; isProfitable: boolean; breakEvenRate: number
}

const STORAGE_KEY = 'quantmatrix_calc2'
const DEFAULTS: CalcInputs = {
  nameA: 'Exchange A', entryA: 50000, exitA: 51000, feeA: 0.06, rateA: 0.01,
  nameB: 'Exchange B', entryB: 50010, exitB: 51010, feeB: 0.06, rateB: -0.005,
  size: 1, leverage: 1, cycles: 1,
}

function loadSaved(): CalcInputs {
  try { const s = localStorage.getItem(STORAGE_KEY); if (s) return { ...DEFAULTS, ...JSON.parse(s) } } catch {}
  return DEFAULTS
}

function calc(i: CalcInputs): CalcResults {
  const n = i.size * i.entryA * i.leverage
  const fi = n * (i.rateA - i.rateB) / 100 * i.cycles
  const pl = ((i.exitA - i.entryA) - (i.exitB - i.entryB)) * i.size * i.leverage
  const tf = n * (i.feeA + i.feeB) / 100 * 2
  const sc = Math.abs(i.entryA - i.entryB) * i.size * i.leverage + Math.abs(i.exitA - i.exitB) * i.size * i.leverage
  const np = fi + pl - tf - sc
  const roi = n > 0 ? (np / n) * 100 : 0
  return { notional: n, fundingIncome: fi, pricePnl: pl, totalFees: tf, spreadCost: sc, netProfit: np, roi, isProfitable: np > 0, breakEvenRate: (tf + sc) / n * 100 / i.cycles }
}

export function ArbitrageCalculator() {
  const [i, setI] = useState<CalcInputs>(loadSaved)
  const [saved, setSaved] = useState(false)
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(i))
    setSaved(true); const t = setTimeout(() => setSaved(false), 2000); return () => clearTimeout(t)
  }, [i])

  const set = (k: keyof CalcInputs, v: string) => { const n = parseFloat(v); if (!isNaN(n)) setI(p => ({ ...p, [k]: n })) }
  const setStr = (k: keyof CalcInputs, v: string) => setI(p => ({ ...p, [k]: v }))

  const r = calc(i)
  const profit = r.isProfitable
  const netC = profit ? 'text-green-500' : 'text-red-500'
  const netBg = profit ? 'bg-green-500/10 border-green-900/30' : 'bg-red-500/10 border-red-900/30'

  const Inp = ({ label, val, setKey, small }: { label: string; val: number | string; setKey: keyof CalcInputs; small?: boolean }) => (
    <div>
      <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">{label}</label>
      <input type={typeof val === 'number' ? 'number' : 'text'} step="any" value={val}
        onChange={e => (typeof val === 'number' ? set : setStr)(setKey, e.target.value)}
        className={`w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors ${small ? 'py-2' : ''}`} />
    </div>
  )

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
            <div className={`flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-wider transition-opacity ${saved ? 'opacity-100' : 'opacity-0'}`}>
              <Save size={10} className="text-green-500" /> <span className="text-green-500">Saved</span>
            </div>
          </div>
        </div>

        <div className="p-8">
          {/* Two Exchange Columns */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Exchange A — Long */}
            <div className="bg-[#0a0a0a] border border-green-900/30 rounded-2xl p-5">
              <div className="text-[10px] font-black text-green-500 uppercase tracking-widest mb-4 flex items-center gap-2"><TrendingUp size={12} /> Long Leg</div>
              <div className="grid grid-cols-2 gap-3">
                <Inp label="Exchange Name" val={i.nameA} setKey="nameA" />
                <Inp label="Funding Rate %" val={i.rateA} setKey="rateA" />
                <Inp label="Entry Price" val={i.entryA} setKey="entryA" />
                <Inp label="Exit Price" val={i.exitA} setKey="exitA" />
                <Inp label="Taker Fee %" val={i.feeA} setKey="feeA" />
              </div>
            </div>
            {/* Exchange B — Short */}
            <div className="bg-[#0a0a0a] border border-red-900/30 rounded-2xl p-5">
              <div className="text-[10px] font-black text-red-500 uppercase tracking-widest mb-4 flex items-center gap-2"><TrendingDown size={12} /> Short Leg</div>
              <div className="grid grid-cols-2 gap-3">
                <Inp label="Exchange Name" val={i.nameB} setKey="nameB" />
                <Inp label="Funding Rate %" val={i.rateB} setKey="rateB" />
                <Inp label="Entry Price" val={i.entryB} setKey="entryB" />
                <Inp label="Exit Price" val={i.exitB} setKey="exitB" />
                <Inp label="Taker Fee %" val={i.feeB} setKey="feeB" />
              </div>
            </div>
          </div>

          {/* Position row */}
          <div className="flex flex-wrap gap-4 mb-8 bg-[#0a0a0a] border border-gray-800 rounded-2xl p-5">
            <div className="flex items-center gap-2 text-[10px] font-black text-gray-600 uppercase tracking-widest mr-2"><Zap size={12} /> Position</div>
            <Inp label="Size (units)" val={i.size} setKey="size" />
            <Inp label="Leverage" val={i.leverage} setKey="leverage" />
            <Inp label="Funding Cycles" val={i.cycles} setKey="cycles" />
            <div className="flex items-center bg-[#111] rounded-xl px-4 border border-gray-800 h-[42px] self-end">
              <span className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mr-2">Notional</span>
              <span className="text-xs font-black text-white">${r.notional.toLocaleString()}</span>
            </div>
          </div>

          {/* Results */}
          <div className={`rounded-2xl border p-6 ${netBg}`}>
            <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-5">P&L Breakdown</div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
              <ResultCard label="Funding Income" val={r.fundingIncome} fmt="$" color={r.fundingIncome >= 0 ? 'text-green-500' : 'text-red-500'} />
              <ResultCard label="Price P&L" val={r.pricePnl} fmt="$" color={r.pricePnl >= 0 ? 'text-green-500' : 'text-red-500'} />
              <ResultCard label="Entry/Exit Spread" val={-r.spreadCost} fmt="$" color="text-yellow-500" />
              <ResultCard label="Trading Fees" val={-r.totalFees} fmt="$" color="text-red-500" />
              <ResultCard label="Net Profit" val={r.netProfit} fmt="$" color={netC} bold />
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
                    &nbsp;·&nbsp;Break-even rate: <span className="text-white">{r.breakEvenRate.toFixed(4)}%</span>/cycle
                  </div>
                </div>
              </div>
              <div className="h-10 w-px bg-gray-800" />
              <div>
                <div className="flex items-center gap-2 mb-1">
                  {profit
                    ? <span className="text-[10px] font-black text-green-500 uppercase tracking-widest">✅ Profit Expected</span>
                    : <span className="text-[10px] font-black text-red-500 uppercase tracking-widest">❌ Loss Expected</span>}
                </div>
                {r.pricePnl !== 0 && (
                  <div className="text-[8px] text-gray-600 font-bold flex items-center gap-1">
                    Price spread: <span className={r.pricePnl > 0 ? 'text-green-500' : 'text-red-500'}>{r.pricePnl > 0 ? '+' : ''}{r.pricePnl.toFixed(2)} USDT</span>
                    &nbsp;(
                    <ArrowRight size={8} /> {i.nameA} {i.entryA.toFixed(2)} → {i.exitA.toFixed(2)}
                    &nbsp;<ArrowLeft size={8} /> {i.nameB} {i.entryB.toFixed(2)} → {i.exitB.toFixed(2)})
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-start gap-3 bg-[#0a0a0a] border border-gray-800 rounded-2xl p-4">
            <AlertTriangle size={14} className="text-yellow-500 shrink-0 mt-0.5" />
            <div className="text-[9px] text-gray-600 leading-relaxed">
              <span className="font-bold text-gray-500">Strategy:</span> Long {i.nameA} (pays funding) + Short {i.nameB} (receives funding). 
              Estimates assume perfect fills at given prices. Actual results vary with slippage, variable funding rates, and latency.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ResultCard({ label, val, fmt, color, bold }: { label: string; val: number; fmt: string; color: string; bold?: boolean }) {
  return (
    <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
      <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-sm ${bold ? 'font-black' : 'font-bold'} ${color}`}>{val >= 0 ? '+' : ''}{fmt}{val.toFixed(2)}</div>
    </div>
  )
}
