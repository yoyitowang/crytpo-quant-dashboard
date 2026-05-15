import { useState } from 'react'
import { X, TrendingUp, TrendingDown, Minus, Zap, DollarSign, Percent, Calculator, AlertTriangle } from 'lucide-react'

interface CalcInputs {
  entryPrice: number
  exitPrice: number
  positionSize: number
  leverage: number
  fundingRateA: number
  fundingRateB: number
  feeMakerA: number
  feeTakerA: number
  feeMakerB: number
  feeTakerB: number
  spreadEntry: number
  spreadExit: number
  holdCycles: number
}

interface CalcResults {
  fundingIncome: number
  tradingFees: number
  spreadCost: number
  netProfit: number
  roi: number
  isProfitable: boolean
  breakEvenFunding: number
}

const DEFAULTS: CalcInputs = {
  entryPrice: 50000,
  exitPrice: 51000,
  positionSize: 1,
  leverage: 1,
  fundingRateA: 0.01,
  fundingRateB: -0.005,
  feeMakerA: 0.02,
  feeTakerA: 0.06,
  feeMakerB: 0.02,
  feeTakerB: 0.06,
  spreadEntry: 0.01,
  spreadExit: 0.01,
  holdCycles: 1,
}

function calculate(inputs: CalcInputs): CalcResults {
  const notional = inputs.positionSize * inputs.entryPrice * inputs.leverage
  const fundingIncome = notional * (inputs.fundingRateA - inputs.fundingRateB) / 100 * inputs.holdCycles
  const feeEntry = notional * (inputs.feeTakerA + inputs.feeTakerB) / 100
  const feeExit = notional * (inputs.feeTakerA + inputs.feeTakerB) / 100
  const tradingFees = feeEntry + feeExit
  const spreadCost = notional * (inputs.spreadEntry + inputs.spreadExit) / 100
  const netProfit = fundingIncome - tradingFees - spreadCost
  const roi = (netProfit / notional) * 100
  const breakEvenFunding = (tradingFees + spreadCost) / notional / inputs.holdCycles * 100

  return {
    fundingIncome,
    tradingFees,
    spreadCost,
    netProfit,
    roi,
    isProfitable: netProfit > 0,
    breakEvenFunding,
  }
}

export function ArbitrageCalculator({ onClose }: { onClose: () => void }) {
  const [inputs, setInputs] = useState<CalcInputs>(DEFAULTS)

  const set = (key: keyof CalcInputs, val: string) => {
    const v = parseFloat(val)
    if (!isNaN(v)) setInputs(prev => ({ ...prev, [key]: v }))
  }

  const results = calculate(inputs)
  const isProfit = results.isProfitable
  const netColor = isProfit ? 'text-green-500' : 'text-red-500'
  const netBg = isProfit ? 'bg-green-500/10 border-green-900/30' : 'bg-red-500/10 border-red-900/30'

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#080808] border border-gray-800 w-full max-w-4xl rounded-[32px] shadow-3xl overflow-hidden relative max-h-[95vh] flex flex-col">
        <div className="h-1.5 bg-gradient-to-r from-blue-600 via-purple-500 to-pink-500 shrink-0" />

        <div className="flex items-center justify-between px-8 py-6 border-b border-gray-900 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/10 rounded-xl">
              <Calculator size={18} className="text-purple-500" />
            </div>
            <div>
              <h2 className="text-lg font-black text-white uppercase tracking-tight">Arbitrage Calculator</h2>
              <p className="text-[9px] font-bold text-gray-600 uppercase tracking-widest mt-0.5">Funding Rate Arbitrage P&L Estimator</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl border border-gray-800 text-gray-600 hover:text-white transition-all">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar p-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Left Column: Position & Funding */}
            <div className="space-y-6">
              <div className="bg-[#0a0a0a] border border-gray-800 rounded-2xl p-5">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-4 flex items-center gap-2"><DollarSign size={12} className="text-blue-500" /> Position</div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Entry Price</label>
                    <input type="number" value={inputs.entryPrice} onChange={e => set('entryPrice', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Exit Price</label>
                    <input type="number" value={inputs.exitPrice} onChange={e => set('exitPrice', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Position Size (units)</label>
                    <input type="number" step="0.01" value={inputs.positionSize} onChange={e => set('positionSize', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Leverage</label>
                    <input type="number" min="1" value={inputs.leverage} onChange={e => set('leverage', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                </div>
              </div>

              <div className="bg-[#0a0a0a] border border-gray-800 rounded-2xl p-5">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-4 flex items-center gap-2"><Percent size={12} className="text-green-500" /> Funding Rates</div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Rate A (long) %</label>
                    <input type="number" step="0.001" value={inputs.fundingRateA} onChange={e => set('fundingRateA', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Rate B (short) %</label>
                    <input type="number" step="0.001" value={inputs.fundingRateB} onChange={e => set('fundingRateB', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div className="col-span-2">
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Funding Cycles (settlements)</label>
                    <input type="number" min="1" value={inputs.holdCycles} onChange={e => set('holdCycles', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Fees & Spread */}
            <div className="space-y-6">
              <div className="bg-[#0a0a0a] border border-gray-800 rounded-2xl p-5">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-4 flex items-center gap-2">Exchange Fees</div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Ex A Taker %</label>
                    <input type="number" step="0.001" value={inputs.feeTakerA} onChange={e => set('feeTakerA', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Ex B Taker %</label>
                    <input type="number" step="0.001" value={inputs.feeTakerB} onChange={e => set('feeTakerB', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Ex A Maker %</label>
                    <input type="number" step="0.001" value={inputs.feeMakerA} onChange={e => set('feeMakerA', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Ex B Maker %</label>
                    <input type="number" step="0.001" value={inputs.feeMakerB} onChange={e => set('feeMakerB', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                </div>
              </div>

              <div className="bg-[#0a0a0a] border border-gray-800 rounded-2xl p-5">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-4 flex items-center gap-2"><Zap size={12} className="text-purple-500" /> Cross-Exchange Spread</div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Entry Spread %</label>
                    <input type="number" step="0.001" value={inputs.spreadEntry} onChange={e => set('spreadEntry', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                  <div>
                    <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Exit Spread %</label>
                    <input type="number" step="0.001" value={inputs.spreadExit} onChange={e => set('spreadExit', e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-purple-600 transition-colors" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Results */}
          <div className="mt-8">
            <div className={`rounded-2xl border p-6 ${netBg}`}>
              <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-5 flex items-center gap-2"><TrendingUp size={12} /> P&L Summary</div>
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
                <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
                  <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">Notional</div>
                  <div className="text-sm font-black text-white">${(inputs.positionSize * inputs.entryPrice * inputs.leverage).toLocaleString()}</div>
                </div>
                <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
                  <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">Funding Income</div>
                  <div className={`text-sm font-black ${results.fundingIncome >= 0 ? 'text-green-500' : 'text-red-500'}`}>{results.fundingIncome >= 0 ? '+' : ''}${results.fundingIncome.toFixed(2)}</div>
                </div>
                <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
                  <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">Trading Fees</div>
                  <div className="text-sm font-black text-red-500">-${results.tradingFees.toFixed(2)}</div>
                </div>
                <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
                  <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">Spread Cost</div>
                  <div className="text-sm font-black text-yellow-500">-${results.spreadCost.toFixed(2)}</div>
                </div>
                <div className="bg-[#111] rounded-xl p-4 border border-gray-800">
                  <div className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1">Net Profit</div>
                  <div className={`text-sm font-black ${netColor}`}>{results.netProfit >= 0 ? '+' : ''}${results.netProfit.toFixed(2)}</div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-6">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-xl ${isProfit ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                    {isProfit ? <TrendingUp size={20} className="text-green-500" /> : <TrendingDown size={20} className="text-red-500" />}
                  </div>
                  <div>
                    <div className={`text-2xl font-black ${netColor}`}>{results.netProfit >= 0 ? '+' : ''}{results.netProfit.toFixed(2)} USDT</div>
                    <div className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mt-0.5">
                      ROI: <span className={netColor}>{results.roi >= 0 ? '+' : ''}{results.roi.toFixed(4)}%</span>
                    </div>
                  </div>
                </div>
                <div className="h-10 w-px bg-gray-800" />
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    {isProfit ? (
                      <span className="text-[10px] font-black text-green-500 uppercase tracking-widest flex items-center gap-1">✅ Profit Expected</span>
                    ) : (
                      <span className="text-[10px] font-black text-red-500 uppercase tracking-widest flex items-center gap-1">❌ Loss Expected</span>
                    )}
                  </div>
                  <div className="text-[8px] text-gray-600 font-bold">
                    Break-even funding rate diff: <span className="text-white">{results.breakEvenFunding.toFixed(4)}%</span> per cycle
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-start gap-3 bg-[#0a0a0a] border border-gray-800 rounded-2xl p-4">
            <AlertTriangle size={14} className="text-yellow-500 shrink-0 mt-0.5" />
            <div className="text-[9px] text-gray-600 leading-relaxed">
              <span className="font-bold text-gray-500">Disclaimer:</span> This calculator provides estimates only. Actual results may vary due to 
              slippage, variable funding rates, exchange latency, and market movements. Always test with small positions first.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
