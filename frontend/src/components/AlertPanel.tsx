import { useState } from 'react'
import { Bell, X, Plus, Trash2, Volume2, VolumeX, AlertTriangle, History } from 'lucide-react'
import type { AlertRule, AlertEvent } from '../types'
import { ALL_EXCHANGES } from '../types'

interface AlertPanelProps {
  rules: AlertRule[]
  events: AlertEvent[]
  soundEnabled: boolean
  onAddRule: (rule: Omit<AlertRule, 'id' | 'enabled' | 'lastTriggeredAt'>) => void
  onRemoveRule: (id: string) => void
  onToggleRule: (id: string) => void
  onToggleSound: () => void
  onClose: () => void
}

export function AlertPanel({ rules, events, soundEnabled, onAddRule, onRemoveRule, onToggleRule, onToggleSound, onClose }: AlertPanelProps) {
  const [tab, setTab] = useState<'rules' | 'history'>('rules')
  const [showForm, setShowForm] = useState(false)
  const [formSymbol, setFormSymbol] = useState('')
  const [formExchange, setFormExchange] = useState('')
  const [formDirection, setFormDirection] = useState<'above' | 'below'>('above')
  const [formThreshold, setFormThreshold] = useState('0.05')

  const handleSubmit = () => {
    const t = parseFloat(formThreshold)
    if (isNaN(t) || t <= 0) return
    onAddRule({
      symbol: formSymbol.trim(),
      exchange: formExchange,
      direction: formDirection,
      threshold: t,
    })
    setFormSymbol('')
    setFormExchange('')
    setFormDirection('above')
    setFormThreshold('0.05')
    setShowForm(false)
  }

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#080808] border border-gray-800 w-full max-w-lg rounded-[32px] shadow-3xl overflow-hidden relative max-h-[90vh] flex flex-col">
        <div className="h-1.5 bg-gradient-to-r from-yellow-600 via-orange-500 to-red-500 shrink-0" />
        
        <div className="flex items-center justify-between px-8 py-6 border-b border-gray-900 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-500/10 rounded-xl">
              <Bell size={18} className="text-yellow-500" />
            </div>
            <div>
              <h2 className="text-lg font-black text-white uppercase tracking-tight">Alerts</h2>
              <p className="text-[9px] font-bold text-gray-600 uppercase tracking-widest mt-0.5">{rules.filter(r => r.enabled).length} Active Rules</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onToggleSound} className={`p-2 rounded-xl border transition-all ${soundEnabled ? 'bg-white/5 border-gray-800 text-gray-400 hover:text-white' : 'bg-transparent border-transparent text-gray-700'}`} title={soundEnabled ? 'Mute' : 'Unmute'}>
              {soundEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
            </button>
            <button onClick={onClose} className="p-2 rounded-xl border border-gray-800 text-gray-600 hover:text-white transition-all">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="flex border-b border-gray-900 px-8 shrink-0">
          <button onClick={() => setTab('rules')} className={`pb-3 pt-2 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all mr-6 ${tab === 'rules' ? 'border-yellow-500 text-white' : 'border-transparent text-gray-600 hover:text-gray-400'}`}>
            <div className="flex items-center gap-2"><Bell size={12} /> Rules</div>
          </button>
          <button onClick={() => setTab('history')} className={`pb-3 pt-2 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all ${tab === 'history' ? 'border-yellow-500 text-white' : 'border-transparent text-gray-600 hover:text-gray-400'}`}>
            <div className="flex items-center gap-2"><History size={12} /> History ({events.length})</div>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
          {tab === 'rules' ? (
            <>
              {rules.length === 0 && !showForm ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <AlertTriangle size={32} className="text-gray-800 mb-4" />
                  <p className="text-[10px] font-black text-gray-700 uppercase tracking-widest mb-1">No Alert Rules</p>
                  <p className="text-[9px] text-gray-800 font-bold uppercase tracking-wider">Configure thresholds for price rate changes</p>
                </div>
              ) : (
                <div className="space-y-2 mb-4">
                  {rules.map(rule => (
                    <div key={rule.id} className={`bg-[#0a0a0a] border rounded-2xl p-4 transition-all ${rule.enabled ? 'border-gray-800' : 'border-gray-900 opacity-40'}`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3 min-w-0">
                          <button onClick={() => onToggleRule(rule.id)} className={`w-5 h-5 rounded-md border flex items-center justify-center transition-all shrink-0 ${rule.enabled ? 'bg-yellow-600 border-yellow-500' : 'border-gray-800'}`}>
                            {rule.enabled && <Bell size={10} className="text-white" />}
                          </button>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-black text-white uppercase">{rule.symbol || 'ANY'}</span>
                              <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded uppercase ${rule.exchange ? 'bg-blue-900/30 text-blue-400' : 'bg-gray-900 text-gray-600'}`}>{rule.exchange || 'ALL'}</span>
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className={`text-[10px] font-bold ${rule.direction === 'above' ? 'text-green-500' : 'text-red-500'}`}>{rule.direction === 'above' ? '>' : '<'}</span>
                              <span className="text-[10px] font-black text-white">{rule.threshold}%</span>
                              {rule.lastTriggeredAt && (
                                <span className="text-[8px] text-gray-700 font-bold">· {new Date(rule.lastTriggeredAt).toLocaleTimeString()}</span>
                              )}
                            </div>
                          </div>
                        </div>
                        <button onClick={() => onRemoveRule(rule.id)} className="p-1.5 text-gray-700 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-all shrink-0">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {showForm ? (
                <div className="bg-[#0a0a0a] border border-gray-800 rounded-2xl p-5">
                  <div className="text-[10px] font-black text-white uppercase tracking-widest mb-4">New Alert Rule</div>
                  <div className="grid grid-cols-2 gap-3 mb-4">
                    <div>
                      <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Symbol</label>
                      <input type="text" value={formSymbol} onChange={e => setFormSymbol(e.target.value)} placeholder="ANY (leave empty)" className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2 text-xs font-bold text-white placeholder:text-gray-700 focus:outline-none focus:border-yellow-600 transition-colors" />
                    </div>
                    <div>
                      <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Exchange</label>
                      <select value={formExchange} onChange={e => setFormExchange(e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2 text-xs font-bold text-white focus:outline-none focus:border-yellow-600 transition-colors appearance-none cursor-pointer">
                        <option value="">ALL Exchanges</option>
                        {ALL_EXCHANGES.map(ex => <option key={ex} value={ex}>{ex}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Direction</label>
                      <select value={formDirection} onChange={e => setFormDirection(e.target.value as 'above' | 'below')} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2 text-xs font-bold text-white focus:outline-none focus:border-yellow-600 transition-colors appearance-none cursor-pointer">
                          <option value="above">Above (&gt;)</option>
                          <option value="below">Below (&lt;)</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-[8px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 block">Threshold (%)</label>
                      <input type="number" step="0.001" min="0.001" value={formThreshold} onChange={e => setFormThreshold(e.target.value)} className="w-full bg-[#111] border border-gray-800 rounded-xl px-3 py-2 text-xs font-bold text-white focus:outline-none focus:border-yellow-600 transition-colors" />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleSubmit} className="flex-1 bg-yellow-600 hover:bg-yellow-500 text-black text-[10px] font-black uppercase tracking-widest py-2.5 rounded-xl transition-all border border-yellow-400">
                      Save Rule
                    </button>
                    <button onClick={() => setShowForm(false)} className="px-6 bg-[#111] text-gray-400 hover:text-white text-[10px] font-black uppercase tracking-widest py-2.5 rounded-xl transition-all border border-gray-800">
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setShowForm(true)} className="w-full flex items-center justify-center gap-2 bg-[#0a0a0a] border border-dashed border-gray-800 hover:border-yellow-600/50 rounded-2xl py-4 text-gray-500 hover:text-yellow-500 transition-all text-[10px] font-black uppercase tracking-widest">
                  <Plus size={14} /> Add Alert Rule
                </button>
              )}
            </>
          ) : (
            <>
              {events.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <History size={32} className="text-gray-800 mb-4" />
                  <p className="text-[10px] font-black text-gray-700 uppercase tracking-widest">No Alert History</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {events.map(ev => (
                    <div key={ev.id} className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-black text-white uppercase">{ev.symbol}</span>
                          <span className="text-[8px] font-bold bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded uppercase">{ev.exchange}</span>
                        </div>
                        <span className="text-[8px] font-bold text-gray-700">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <div className="flex items-baseline gap-1.5">
                        <span className={`text-base font-black ${ev.rate > 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {ev.rate > 0 ? '+' : ''}{ev.rate.toFixed(4)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
