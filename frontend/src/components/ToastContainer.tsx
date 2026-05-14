import { AlertTriangle, X } from 'lucide-react'
import type { AlertEvent } from '../types'

interface ToastContainerProps {
  events: AlertEvent[]
  activeToastIds: string[]
  onDismiss: (id: string) => void
}

export function ToastContainer({ events, activeToastIds, onDismiss }: ToastContainerProps) {
  const activeEvents = events.filter(e => activeToastIds.includes(e.id))

  if (activeEvents.length === 0) return null

  return (
    <div className="fixed top-20 right-6 z-[200] flex flex-col gap-3 pointer-events-none">
      {activeEvents.map((ev, i) => (
        <div
          key={ev.id}
          className="pointer-events-auto animate-in slide-in-from-right-8 fade-in duration-300"
          style={{ animationFillMode: 'both' }}
        >
          <div className="bg-[#0a0a0a] border border-gray-800 rounded-2xl shadow-3xl overflow-hidden w-80 backdrop-blur-xl">
            <div className={`h-1 ${ev.rate > 0 ? 'bg-green-500' : 'bg-red-500'}`} />
            <div className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <div className={`p-1.5 rounded-lg ${ev.rate > 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                    <AlertTriangle size={14} className={ev.rate > 0 ? 'text-green-500' : 'text-red-500'} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-black text-white uppercase truncate">{ev.symbol}</span>
                      <span className="text-[8px] font-bold bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded uppercase">{ev.exchange}</span>
                    </div>
                    <p className="text-[9px] font-bold text-gray-600 uppercase tracking-wider mt-0.5">Alert Triggered</p>
                  </div>
                </div>
                <button onClick={() => onDismiss(ev.id)} className="text-gray-700 hover:text-white transition-colors shrink-0">
                  <X size={14} />
                </button>
              </div>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className={`text-lg font-black ${ev.rate > 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {ev.rate > 0 ? '+' : ''}{ev.rate.toFixed(4)}%
                </span>
                <span className="text-[9px] font-bold text-gray-700 uppercase">Funding Rate</span>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
