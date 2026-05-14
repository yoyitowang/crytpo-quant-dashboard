import { useState, useCallback, useRef, useEffect } from 'react'
import type { AlertRule, AlertEvent, FundingRate } from '../types'

const STORAGE_KEY = 'quantmatrix_alert_rules'
const SOUND_KEY = 'quantmatrix_alert_sound'
const MAX_EVENTS = 50
const MAX_TOASTS = 5
const TOAST_DURATION = 5000

let idCounter = 0
function uid(): string {
  return `${Date.now().toString(36)}-${++idCounter}`
}

function loadRules(): AlertRule[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? JSON.parse(saved) : []
  } catch {
    return []
  }
}

export function useAlerts() {
  const [rules, setRules] = useState<AlertRule[]>(loadRules)
  const [events, setEvents] = useState<AlertEvent[]>([])
  const [activeToastIds, setActiveToastIds] = useState<string[]>([])
  const [soundEnabled, setSoundEnabled] = useState(() => localStorage.getItem(SOUND_KEY) !== 'false')

  const prevRatesRef = useRef<Record<string, FundingRate>>({})
  const rulesRef = useRef(rules)
  const soundRef = useRef(soundEnabled)
  const toastTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  rulesRef.current = rules
  soundRef.current = soundEnabled

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(rules))
  }, [rules])

  const addRule = useCallback((rule: Omit<AlertRule, 'id' | 'enabled' | 'lastTriggeredAt'>) => {
    setRules(prev => [...prev, { ...rule, id: uid(), enabled: true, lastTriggeredAt: null }])
  }, [])

  const removeRule = useCallback((id: string) => {
    setRules(prev => prev.filter(r => r.id !== id))
  }, [])

  const toggleRule = useCallback((id: string) => {
    setRules(prev => prev.map(r => r.id === id ? { ...r, enabled: !r.enabled } : r))
  }, [])

  const toggleSound = useCallback(() => {
    setSoundEnabled(prev => {
      const next = !prev
      localStorage.setItem(SOUND_KEY, String(next))
      return next
    })
  }, [])

  const dismissToast = useCallback((eventId: string) => {
    setActiveToastIds(prev => prev.filter(id => id !== eventId))
    const timer = toastTimers.current.get(eventId)
    if (timer) {
      clearTimeout(timer)
      toastTimers.current.delete(eventId)
    }
  }, [])

  const scheduleDismiss = useCallback((eventId: string) => {
    const existing = toastTimers.current.get(eventId)
    if (existing) clearTimeout(existing)
    const timer = setTimeout(() => dismissToast(eventId), TOAST_DURATION)
    toastTimers.current.set(eventId, timer)
  }, [dismissToast])

  const beep = useCallback(() => {
    if (!soundRef.current) return
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.frequency.value = 880
      osc.type = 'sine'
      gain.gain.setValueAtTime(0.25, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4)
      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.4)
      setTimeout(() => ctx.close(), 500)
    } catch { /* audio unavailable */ }
  }, [])

  const checkAlerts = useCallback((rates: Record<string, FundingRate>) => {
    const currentRules = rulesRef.current
    if (currentRules.length === 0) return

    const prev = prevRatesRef.current
    prevRatesRef.current = rates

    const newEvents: AlertEvent[] = []
    const triggeredIds = new Set<string>()

    currentRules.filter(r => r.enabled).forEach(rule => {
      const symFilter = rule.symbol && rule.symbol !== '*'
      const exFilter = rule.exchange && rule.exchange !== '*'

      Object.values(rates).forEach(rate => {
        if (symFilter && !rate.symbol.toLowerCase().includes(rule.symbol.toLowerCase())) return
        if (exFilter && rate.exchange !== rule.exchange) return

        const prevRate = prev[`${rate.exchange}:${rate.symbol}`]
        if (!prevRate) return

        const ratePct = rate.rate * 100
        const prevPct = prevRate.rate * 100
        const threshold = rule.threshold

        const crossed = rule.direction === 'above'
          ? (ratePct > threshold && prevPct <= threshold)
          : (ratePct < threshold && prevPct >= threshold)

        if (crossed) {
          newEvents.push({
            id: uid(),
            ruleId: rule.id,
            symbol: rate.symbol,
            exchange: rate.exchange,
            rate: ratePct,
            message: `${rate.symbol} @ ${rate.exchange} ${ratePct > 0 ? '+' : ''}${ratePct.toFixed(4)}%`,
            timestamp: Date.now(),
          })
          triggeredIds.add(rule.id)
        }
      })
    })

    if (triggeredIds.size > 0) {
      setRules(prev => prev.map(r => triggeredIds.has(r.id) ? { ...r, lastTriggeredAt: Date.now() } : r))
    }

    if (newEvents.length > 0) {
      setEvents(prev => [...newEvents, ...prev].slice(0, MAX_EVENTS))
      setActiveToastIds(prev => {
        const ids = newEvents.map(e => e.id)
        const combined = [...ids, ...prev].slice(0, MAX_TOASTS)
        ids.forEach(id => scheduleDismiss(id))
        return combined
      })
      beep()
    }
  }, [beep, scheduleDismiss])

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      toastTimers.current.forEach(t => clearTimeout(t))
      toastTimers.current.clear()
    }
  }, [])

  return {
    rules, events, activeToastIds, soundEnabled,
    addRule, removeRule, toggleRule, toggleSound, dismissToast, checkAlerts,
  } as const
}
