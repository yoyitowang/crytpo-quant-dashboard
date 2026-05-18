import { useState, useEffect, useCallback, useMemo, useRef, memo } from 'react';
import { Search, BarChart3, ArrowUpDown, ChevronLeft, ChevronRight, ChevronDown, Zap, Grid, LayoutGrid, Clock, Filter, CheckSquare, Square, TrendingUp, TrendingDown, Layers, Activity, Globe, ShieldCheck, AlertTriangle, Monitor, ExternalLink, X, Eye, EyeOff, Bell, Calculator, Star } from 'lucide-react';
import { createChart, ColorType, IChartApi } from 'lightweight-charts';
import type { FundingRate } from './types';
import { EXCHANGE_COLORS, ALL_EXCHANGES } from './types';
import { useAlerts } from './hooks/useAlerts';
import { AlertPanel } from './components/AlertPanel';
import { ToastContainer } from './components/ToastContainer';
import { ArbitrageCalculator } from './components/ArbitrageCalculator';

// --- TradingView 專業圖表組件 (支援動態隱藏) ---
const TVChartRaw = ({ data, isCompare = false, visibleExchanges = ALL_EXCHANGES }: { data: any, isCompare?: boolean, visibleExchanges?: string[] }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<Record<string, any>>({});
    const [error, setError] = useState('');

    // Create chart once on mount (re-create if isCompare changes)
    useEffect(() => {
        if (!containerRef.current) return;
        try {
            if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
            seriesRef.current = {};
            const chart = createChart(containerRef.current, {
                layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#888' },
                grid: { vertLines: { color: '#111' }, horzLines: { color: '#111' } },
                width: containerRef.current.clientWidth,
                height: isCompare ? 500 : 350,
                timeScale: { borderColor: '#222', timeVisible: true, secondsVisible: false },
            });
            chartRef.current = chart;
            setError('');
            const handleResize = () => { if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth }); };
            window.addEventListener('resize', handleResize);
            return () => { window.removeEventListener('resize', handleResize); try { chart.remove(); } catch {}; chartRef.current = null; seriesRef.current = {}; };
        } catch (e: any) { setError('Chart init failed: ' + (e.message || e)); }
    }, [isCompare]);

    // When data changes → rebuild all series
    useEffect(() => {
        if (!chartRef.current || !data) return;
        const chart = chartRef.current;
        setError('');
        try {
            // Remove all old series
            Object.values(seriesRef.current).forEach((s: any) => { try { chart.removeSeries(s); } catch {} });
            seriesRef.current = {};

            if (isCompare) {
                Object.keys(data).forEach((ex) => {
                    const exData = data[ex];
                    if (!Array.isArray(exData) || exData.length === 0) return;
                    const isVisible = visibleExchanges.includes(ex);
                    const lineSeries = chart.addLineSeries({
                        color: EXCHANGE_COLORS[ex] || '#888', lineWidth: 2, title: ex.toUpperCase(),
                        visible: isVisible,
                        priceFormat: { type: 'custom', formatter: (price: number) => price.toFixed(4) + '%', minMove: 0.0001 }
                    });
                    const sorted = [...exData]
                        .sort((a: any, b: any) => a.time - b.time || -1)
                        .filter((d: any, i: number, arr: any[]) => i === 0 || d.time !== arr[i-1].time)
                        .map((d: any) => ({ ...d, value: d.value * 100 }));
                    lineSeries.setData(sorted);
                    if (isVisible && sorted.length > 0) {
                        const avg = sorted.reduce((acc: number, cur: any) => acc + cur.value, 0) / sorted.length;
                        lineSeries.createPriceLine({ price: avg, color: EXCHANGE_COLORS[ex] || '#888', lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: `AVG (${ex.toUpperCase()}): ${avg.toFixed(4)}%` });
                    }
                    seriesRef.current[ex] = lineSeries;
                });
            } else if (Array.isArray(data) && data.length > 0) {
                const baselineSeries = chart.addBaselineSeries({
                    baseValue: { type: 'price', value: 0 },
                    topLineColor: '#10b981', topFillColor1: 'rgba(16, 185, 129, 0.4)', topFillColor2: 'rgba(16, 185, 129, 0.05)',
                    bottomLineColor: '#ef4444', bottomFillColor1: 'rgba(239, 68, 68, 0.05)', bottomFillColor2: 'rgba(239, 68, 68, 0.4)',
                    lineWidth: 3, priceFormat: { type: 'custom', formatter: (price: number) => price.toFixed(4) + '%', minMove: 0.0001 }
                });
                const sorted = [...data]
                    .sort((a: any, b: any) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime() || -1)
                    .filter((d: any, i: number, arr: any[]) => i === 0 || new Date(d.timestamp).getTime() !== new Date(arr[i-1].timestamp).getTime())
                    .map((d: any) => ({ time: new Date(d.timestamp).getTime() / 1000, value: d.rate * 100 }));
                baselineSeries.setData(sorted);
                if (sorted.length > 0) {
                    const avg = sorted.reduce((acc: number, cur: any) => acc + cur.value, 0) / sorted.length;
                    baselineSeries.createPriceLine({ price: avg, color: '#3B82F6', lineWidth: 2, lineStyle: 3, axisLabelVisible: true, title: `AVERAGE APR: ${avg.toFixed(4)}%` });
                }
                seriesRef.current['_single'] = baselineSeries;
            }
            try { chart.timeScale().fitContent(); } catch {}
        } catch (e: any) { setError('Chart render error: ' + (e.message || e)); }
    }, [data, isCompare]);

    // When visibility changes → toggle existing series (NO chart recreation)
    useEffect(() => {
        if (!data) return;
        Object.entries(seriesRef.current).forEach(([ex, series]: [string, any]) => {
            if (ex === '_single') return;
            try { series.applyOptions({ visible: visibleExchanges.includes(ex) }); } catch {}
        });
    }, [visibleExchanges]);

    if (error) return <div className="text-red-500 text-[10px] p-4 text-center">{error}</div>;
    return <div ref={containerRef} className="w-full" style={{ height: isCompare ? 500 : 350 }} />;
};
const TVChart = memo(TVChartRaw);

function App() {
  const [rates, setRates] = useState<Record<string, FundingRate>>({});
  const [summary, setSummary] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [isAlertPanelOpen, setIsAlertPanelOpen] = useState(false);
  const { rules, events, activeToastIds, soundEnabled, addRule, removeRule, toggleRule, toggleSound, dismissToast, checkAlerts } = useAlerts();
  const [history, setHistory] = useState<any[]>([]);
  const [multiHistory, setMultiHistory] = useState<any>(null);
  const [selectedPair, setSelectedPair] = useState<{exchange: string, symbol: string} | null>(null);
  const [compareSymbol, setCompareSymbol] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<number>(7);
  const [visibleExchanges, setVisibleExchanges] = useState<string[]>(ALL_EXCHANGES);
  const [connected, setConnected] = useState(false);
  const [viewMode, setViewMode] = useState<'matrix' | 'heatplot' | 'calc' | 'watch'>('matrix');
  const [dataMode, setDataMode] = useState<'funding' | 'all' | 'price'>('funding');
  const [search, setSearch] = useState('');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);
  const [selectedExchanges, setSelectedExchanges] = useState<string[]>(() => {
    const saved = localStorage.getItem('quantmatrix_exchanges');
    if (saved) {
        try { return JSON.parse(saved); } catch (e) { return ALL_EXCHANGES; }
    }
    return ALL_EXCHANGES;
  });

  useEffect(() => {
    localStorage.setItem('quantmatrix_exchanges', JSON.stringify(selectedExchanges));
  }, [selectedExchanges]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
        if (filterRef.current && !filterRef.current.contains(event.target as Node)) {
            setIsFilterOpen(false);
        }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);
  const [sortConfig, setSortConfig] = useState<{key: string, direction: 'asc' | 'desc'}>({key: 'spread', direction: 'desc'});
  const [favorites, setFavorites] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('quantmatrix_favorites') || '[]') } catch { return [] }
  });

  useEffect(() => { localStorage.setItem('quantmatrix_favorites', JSON.stringify(favorites)) }, [favorites]);

  const toggleFav = (sym: string) => {
    setFavorites(prev => prev.includes(sym) ? prev.filter(s => s !== sym) : [...prev, sym]);
  };

  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingMulti, setLoadingMulti] = useState(false);
  const CACHE_TTL = 30 * 60 * 1000;
  const MAX_CACHE_SIZE = 50;
  const cacheRef = useRef<Map<string, {data: any, time: number}>>(new Map());
  const cacheGet = useCallback(<T,>(key: string): T | null => {
    const entry = cacheRef.current.get(key);
    if (!entry) return null;
    if (Date.now() - entry.time > CACHE_TTL) {
      cacheRef.current.delete(key);
      return null;
    }
    cacheRef.current.delete(key);
    cacheRef.current.set(key, entry);
    return entry.data as T;
  }, []);
  const cacheSet = useCallback((key: string, data: any) => {
    if (cacheRef.current.has(key)) {
      cacheRef.current.get(key)!.time = Date.now();
      return;
    }
    if (cacheRef.current.size >= MAX_CACHE_SIZE) {
      const oldestKey = cacheRef.current.keys().next().value;
      if (oldestKey !== undefined) cacheRef.current.delete(oldestKey);
    }
    cacheRef.current.set(key, {data, time: Date.now()});
  }, []);
  const [symbolInventory, setSymbolInventory] = useState<Record<string, string[]> | null>(null);

  const LoadingSpinner = ({ label }: { label?: string }) => (
    <div className="flex flex-col items-center justify-center gap-4 py-12">
        <div className="relative w-12 h-12">
            <div className="absolute inset-0 border-4 border-blue-500/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-transparent border-t-blue-500 rounded-full animate-spin [animation-duration:1.5s]"></div>
        </div>
        {label && <p className="text-[10px] font-black text-gray-600 uppercase tracking-[0.2em] animate-pulse">{label}</p>}
    </div>
  );

  const TimeframeSelector = () => (
    <div className="flex bg-[#111] p-1 rounded-lg border border-gray-800 shadow-inner">
        {[7, 14, 30].map(d => (
            <button 
                key={d} 
                onClick={() => setTimeframe(d)} 
                className={`px-3 py-1 rounded-md text-[10px] font-black uppercase transition-all ${timeframe === d ? 'bg-blue-600 text-white shadow-lg border border-blue-400' : 'text-gray-500 hover:text-gray-300 border border-transparent'}`}
            >
                {d}D
            </button>
        ))}
    </div>
  );

  const formatLocalTime = (isoStr: string | undefined) => {
    if (!isoStr || isoStr === "None") return "--:--:--";
    try {
        const date = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z');
        return date.toLocaleString();
    } catch (e) { return isoStr; }
  };

  const formatPrice = (price: number) => {
    const abs = Math.abs(price);
    let decimals: number;
    if (abs >= 10000) decimals = 2;
    else if (abs >= 100) decimals = 4;
    else if (abs >= 1) decimals = 6;
    else if (abs >= 0.01) decimals = 8;
    else decimals = 10;
    return '$' + price.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  };

  const connectWebSocket = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => setConnected(true);
    
    // 實施緩衝區，每秒更新一次狀態，避免 React 高頻率渲染
    let buffer: FundingRate[] = [];
    const flushBuffer = () => {
      if (buffer.length === 0) return;
      setRates(prev => {
        const next = {...prev};
        buffer.forEach(i => { if(i?.exchange && i?.symbol) next[`${i.exchange}:${i.symbol}`] = i; });
        buffer = [];
        return next;
      });
    };
    const interval = setInterval(flushBuffer, 1000);

    ws.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            const items = Array.isArray(data) ? data : [data];
            buffer.push(...items);
        } catch {}
    };
    ws.onclose = () => { 
      setConnected(false); 
      clearInterval(interval);
      setTimeout(connectWebSocket, 3000); 
    };
    return ws;
  }, []);

  useEffect(() => { const ws = connectWebSocket(); return () => ws.close(); }, [connectWebSocket]);

  // --- 優化：秒開邏輯 (LocalStorage + Compressed API) ---
  useEffect(() => {
    // 1. 優先從本地緩存讀取 (秒開)
    const cached = localStorage.getItem('quantmatrix_rates_cache');
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        if (Object.keys(parsed).length > 0) setRates(parsed);
      } catch (e) { console.error("Cache load error", e); }
    }

    const fetchData = async () => {
        // 2. 使用壓縮版 API 獲取全市場數據
        try {
          const res = await fetch('/api/rates/compressed');
          const data = await res.json();
          if (Array.isArray(data)) {
            const initialRates: Record<string, FundingRate> = {};
            data.forEach(([sym, ex, rate, interval, markPrice]) => {
              initialRates[`${ex}:${sym}`] = {
                symbol: sym, exchange: ex, rate, interval,
                mark_price: markPrice ?? undefined,
                timestamp: new Date().toISOString()
              };
            });
            setRates(prev => ({...prev, ...initialRates}));
            // 寫回快存
            localStorage.setItem('quantmatrix_rates_cache', JSON.stringify(initialRates));
          }
        } catch (e) { console.error("Fetch compressed error", e); }

        fetch('/api/analysis/summary').then(res => res.json()).then(setSummary);
        fetch('/api/health/ready').then(res => res.json()).then(setHealth);
        fetch('/api/symbols').then(res => res.json()).then(data => {
            if (data && typeof data === 'object' && Object.keys(data).length > 0) setSymbolInventory(data);
        }).catch(() => {});
    };
    fetchData();
    const interval = setInterval(fetchData, 30000); // 延長 API 輪詢間隔，主要靠 WS 更新
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    checkAlerts(rates);
  }, [rates, checkAlerts]);

  useEffect(() => {
    if (selectedPair) {
        const cacheKey = `${selectedPair.exchange}_${selectedPair.symbol}_${timeframe}`;
        const cached = cacheGet<any[]>(cacheKey);
        if (cached) {
            setHistory(cached);
            setLoadingHistory(false);
            return;
        }

        setHistory([]);
        setLoadingHistory(true);
        fetch(`/api/rates/history/${selectedPair.exchange}/${selectedPair.symbol}?days=${timeframe}`)
            .then(res => res.json())
            .then(data => {
                const res = Array.isArray(data) ? data : [];
                setHistory(res);
                cacheSet(cacheKey, res);
                setLoadingHistory(false);
            })
            .catch(() => setLoadingHistory(false));
    }
  }, [selectedPair, timeframe]);

  useEffect(() => {
    if (compareSymbol) {
        const cacheKey = `all_${compareSymbol}_${timeframe}`;
        const cached = cacheGet<any>(cacheKey);
        if (cached) {
            const hist = cached?.data || cached;
            setMultiHistory(hist);
            setLoadingMulti(false);
            return;
        }

        setMultiHistory({});
        setLoadingMulti(true);
        fetch(`/api/rates/history_all/${compareSymbol}?days=${timeframe}`)
            .then(res => res.json())
            .then(data => {
                const hist = data.data || data;
                setMultiHistory(hist);
                cacheSet(cacheKey, data);
                setLoadingMulti(false);
            })
            .catch(() => {
                setLoadingMulti(false);
            });
        setVisibleExchanges(ALL_EXCHANGES); 
    } else { setMultiHistory(null); }
  }, [compareSymbol, timeframe]);

  const filteredData = useMemo(() => {
    const symbolsMap: Record<string, Record<string, {rate: number, interval: number, markPrice?: number}>> = {};
    Object.values(rates).forEach(r => {
        if (!symbolsMap[r.symbol]) symbolsMap[r.symbol] = {};
        symbolsMap[r.symbol][r.exchange] = { rate: r.rate, interval: r.interval || 8, markPrice: r.mark_price };
    });

    let result = Object.keys(symbolsMap).map(sym => {
        const activeAPRs = Object.entries(symbolsMap[sym])
            .filter(([ex]) => selectedExchanges.includes(ex))
            .map(([_, d]) => d.rate * (24 / d.interval) * 365);
            
        // 修正：取絕對值最大，因為正負費率皆可獲利 (Long/Short 獲利潛力)
        const maxAprMagnitude = activeAPRs.length > 0 ? Math.max(...activeAPRs.map(Math.abs)) : 0;
        const actualMax = activeAPRs.length > 0 ? Math.max(...activeAPRs) : 0;
        const actualMin = activeAPRs.length > 0 ? Math.min(...activeAPRs) : 0;
        const spread = activeAPRs.length > 1 ? (actualMax - actualMin) : 0;

        const activePrices = Object.entries(symbolsMap[sym])
            .filter(([ex]) => selectedExchanges.includes(ex))
            .map(([_, d]) => d.markPrice)
            .filter((p): p is number => p !== undefined && p !== null);
        const maxPrice = activePrices.length > 0 ? Math.max(...activePrices) : 0;
        const minPrice = activePrices.length > 0 ? Math.min(...activePrices) : 0;
        const priceSpread = activePrices.length > 1 ? (maxPrice - minPrice) : 0;

        return { 
            symbol: sym, 
            rates: Object.fromEntries(Object.entries(symbolsMap[sym]).map(([ex, d]) => [ex, d.rate])), 
            intervals: Object.fromEntries(Object.entries(symbolsMap[sym]).map(([ex, d]) => [ex, d.interval])),
            markPrices: Object.fromEntries(Object.entries(symbolsMap[sym]).map(([ex, d]) => [ex, d.markPrice])),
            maxApr: maxAprMagnitude * 100,
            spread: spread * 100,
            maxPrice,
            priceSpread,
            base: sym.replace(/USDT|USDC/i, ''), 
            quote: sym.includes('USDC') ? 'USDC' : 'USDT' 
        };
    });

    if (search) result = result.filter(r => r.symbol.toLowerCase().includes(search.toLowerCase()));
    result.sort((a, b) => {
        let v1: any, v2: any;
        if (sortConfig.key === 'symbol') { v1 = a.symbol; v2 = b.symbol; }
        else if (sortConfig.key === 'maxApr') { v1 = a.maxApr > 0 ? a.maxApr : undefined; v2 = b.maxApr > 0 ? b.maxApr : undefined; }
        else if (sortConfig.key === 'spread') { v1 = a.spread > 0 ? a.spread : undefined; v2 = b.spread > 0 ? b.spread : undefined; }
        else if (sortConfig.key === 'maxPrice') { v1 = a.maxPrice > 0 ? a.maxPrice : undefined; v2 = b.maxPrice > 0 ? b.maxPrice : undefined; }
        else if (sortConfig.key === 'priceSpread') { v1 = a.priceSpread > 0 ? a.priceSpread : undefined; v2 = b.priceSpread > 0 ? b.priceSpread : undefined; }
        else { v1 = a.rates[sortConfig.key]; v2 = b.rates[sortConfig.key]; }
        if (v1 === undefined) return 1; if (v2 === undefined) return -1;
        const res = v1 > v2 ? 1 : -1;
        return sortConfig.direction === 'asc' ? res : -res;
    });
    return result;
  }, [rates, search, selectedExchanges, sortConfig]);

  const currentSymbols = filteredData.slice((page - 1) * pageSize, page * pageSize);
  const totalPages = Math.max(1, Math.ceil(filteredData.length / pageSize));

  // 動態計算 Top Payers/Receivers (基於目前選中的交易所)
  const { topPayers, topReceivers } = useMemo(() => {
    const allSelectedRates = Object.values(rates).filter(r => selectedExchanges.includes(r.exchange));
    return {
      topPayers: [...allSelectedRates].sort((a, b) => b.rate - a.rate).slice(0, 5),
      topReceivers: [...allSelectedRates].sort((a, b) => a.rate - b.rate).slice(0, 5)
    };
  }, [rates, selectedExchanges]);

  const handleSort = (key: string) => {
    setSortConfig(prev => ({ key, direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc' }));
    setPage(1);
  };

  const toggleExchangeVisibility = (ex: string) => {
    setVisibleExchanges(prev => prev.includes(ex) ? prev.filter(e => e !== ex) : [...prev, ex]);
  };

  return (
    <div className="min-h-screen bg-[#000] text-gray-400 font-sans selection:bg-blue-500/30">
      <nav className="bg-[#080808] border-b border-gray-900 sticky top-0 z-50 px-6 py-3 flex flex-wrap justify-between items-center gap-4 shadow-2xl">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <Zap size={22} className="text-blue-500 fill-blue-500" />
            <h1 className="text-xl font-black text-white italic tracking-tighter uppercase">QuantMatrix v11.6</h1>
          </div>
             <div className="flex bg-[#111] p-1 rounded-lg border border-gray-800">
                <button onClick={() => setViewMode('matrix')} className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase flex items-center gap-2 transition-all ${viewMode === 'matrix' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500'}`}><LayoutGrid size={14}/> Matrix</button>
                <button onClick={() => setViewMode('heatplot')} className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase flex items-center gap-2 transition-all ${viewMode === 'heatplot' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500'}`}><Grid size={14}/> Heatplot</button>
                <button onClick={() => setViewMode('calc')} className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase flex items-center gap-2 transition-all ${viewMode === 'calc' ? 'bg-purple-600 text-white shadow-lg' : 'text-gray-500'}`}><Calculator size={14}/> Calc</button>
                <button onClick={() => setViewMode('watch')} className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase flex items-center gap-2 transition-all ${viewMode === 'watch' ? 'bg-yellow-600 text-white shadow-lg' : 'text-gray-500'}`}><Star size={14}/> Watch</button>
             </div>
             <div className="flex bg-[#111] p-1 rounded-lg border border-gray-800 gap-0.5">
                <button onClick={() => setDataMode('funding')} className={`px-3 py-1.5 rounded-md text-[10px] font-black uppercase transition-all ${dataMode === 'funding' ? 'bg-green-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'}`}>Funding</button>
                <button onClick={() => setDataMode('all')} className={`px-3 py-1.5 rounded-md text-[10px] font-black uppercase transition-all ${dataMode === 'all' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'}`}>All</button>
                <button onClick={() => setDataMode('price')} className={`px-3 py-1.5 rounded-md text-[10px] font-black uppercase transition-all ${dataMode === 'price' ? 'bg-amber-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'}`}>Price</button>
             </div>
        </div>
        <div className="flex items-center gap-6">
            <div className="flex flex-col items-end">
                <div className="text-[10px] font-black uppercase tracking-tighter"><span className="text-gray-600">Last Sync:</span> <span className="text-blue-500">{formatLocalTime(health?.last_update)}</span></div>
                <div className="flex items-center gap-2 mt-0.5"><div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} /><span className="text-[9px] font-bold text-gray-700 uppercase">Engine: {connected ? 'Online' : 'Offline'}</span></div>
            </div>
            <button onClick={() => setIsAlertPanelOpen(true)} className="relative p-2 rounded-xl border border-gray-800 hover:border-yellow-600/50 hover:text-yellow-500 text-gray-500 transition-all">
              <Bell size={16} />
              {rules.some(r => r.enabled) && <span className="absolute -top-1 -right-1 w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />}
            </button>
            <input type="text" placeholder="SEARCH ASSET..." className="bg-[#111] border border-gray-800 rounded-full px-6 py-1.5 text-xs focus:outline-none focus:border-blue-900 w-48 font-bold uppercase" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </nav>

      <main className="w-[98%] max-w-[2000px] mx-auto p-4 md:p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg relative group">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1">Market Sentiment</div>
                <div className={`text-2xl font-black italic tracking-tighter ${summary?.market_sentiment === 'Bullish' ? 'text-green-500' : 'text-red-500'}`}>{summary?.market_sentiment || 'NEUTRAL'}</div>
                <div className="flex items-center gap-2 mt-3">
                    <div className="flex-1 h-1.5 bg-gray-900 rounded-full overflow-hidden flex">
                        <div className="h-full bg-green-500" style={{ width: `${50 + (summary?.avg_apr || 0) * 100}%` }}></div>
                        <div className="h-full bg-red-500" style={{ width: `${50 - (summary?.avg_apr || 0) * 100}%` }}></div>
                    </div>
                </div>
            </div>
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg">
               <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-3 flex items-center gap-2"><TrendingUp size={12} className="text-green-500"/> Top Payers</div>
               <div className="space-y-1.5">{topPayers.map((r, i) => (
                   <div key={i} className="flex justify-between items-center text-[11px]">
                       <span className="font-bold text-gray-300 font-mono">{r.symbol} <span className="text-[8px] bg-blue-900/30 text-blue-400 px-1 rounded ml-1 uppercase">{r.exchange}</span></span>
                       <span className="font-black text-green-400">{(r.rate * 100).toFixed(4)}%</span>
                   </div>
               ))}</div>
            </div>
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg">
               <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-3 flex items-center gap-2"><TrendingDown size={12} className="text-red-500"/> Top Receivers</div>
               <div className="space-y-1.5">{topReceivers.map((r, i) => (
                   <div key={i} className="flex justify-between items-center text-[11px]">
                       <span className="font-bold text-gray-300 font-mono">{r.symbol} <span className="text-[8px] bg-red-900/30 text-red-400 px-1 rounded ml-1 uppercase">{r.exchange}</span></span>
                       <span className="font-black text-red-400">{(r.rate * 100).toFixed(4)}%</span>
                   </div>
               ))}</div>
            </div>            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg flex flex-col justify-center">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1 flex items-center gap-2"><ShieldCheck size={14} className="text-blue-500"/> System Core</div>
                <div className="text-3xl font-black text-white">{filteredData.length}</div>
                <div className="text-[9px] font-bold text-gray-700 uppercase tracking-tighter">Monitoring {Object.keys(rates).length} Active Channels</div>
            </div>
        </div>

        {selectedPair && (
            <div className="mb-8 animate-in zoom-in-95 duration-500">
                <div className="bg-[#080808] border border-blue-900/30 rounded-3xl p-6 shadow-2xl relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-0.5 bg-blue-600/50"></div>
                    <div className="flex justify-between items-center mb-6">
                        <div className="flex items-center gap-4">
                            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white"><BarChart3 size={20} /></div>
                            <div>
                                <h3 className="text-xl font-black text-white uppercase italic tracking-tighter">{selectedPair.symbol} <span className="text-blue-500 text-sm uppercase">{selectedPair.exchange}</span></h3>
                                <p className="text-[9px] font-bold text-gray-600 uppercase tracking-[0.2em]">Institutional Historical Analysis</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            <TimeframeSelector />
                            <button onClick={() => setSelectedPair(null)} className="text-gray-600 hover:text-white transition-colors"><X size={20}/></button>
                        </div>
                    </div>
                    <div className="min-h-[350px] w-full flex items-center justify-center">
                        {loadingHistory ? (
                            <LoadingSpinner label="Fetching Live Exchange History..." />
                        ) : history.length > 0 ? (
                            <TVChart key={`single-${selectedPair?.exchange}-${selectedPair?.symbol}`} data={history} />
                        ) : (
                            <div className="text-gray-800 font-black uppercase text-[10px] tracking-widest">No historical data available for this pair</div>
                        )}
                    </div>
                </div>
            </div>
        )}

        <div className="flex justify-between items-center mb-6">
            <div className="relative" ref={filterRef}>
                <button 
                    onClick={() => setIsFilterOpen(!isFilterOpen)}
                    className={`flex items-center gap-3 px-6 py-2.5 rounded-xl border font-black uppercase text-[10px] tracking-widest transition-all ${isFilterOpen ? 'bg-blue-600 border-blue-400 text-white shadow-lg shadow-blue-900/20' : 'bg-[#080808] border-gray-900 text-gray-400 hover:border-gray-700'}`}
                >
                    <Filter size={14} className={isFilterOpen ? 'text-white' : 'text-blue-500'} />
                    Exchanges ({selectedExchanges.length}/{ALL_EXCHANGES.length})
                    <ChevronDown size={14} className={`transition-transform duration-300 ${isFilterOpen ? 'rotate-180' : ''}`} />
                </button>

                {isFilterOpen && (
                    <div className="absolute left-0 mt-3 w-64 bg-[#0a0a0a] border border-gray-800 rounded-2xl shadow-3xl z-[60] overflow-hidden animate-in slide-in-from-top-2 duration-200">
                        <div className="p-3 border-b border-gray-900 flex gap-2">
                            <button 
                                onClick={() => { setSelectedExchanges(ALL_EXCHANGES); setPage(1); }}
                                className="flex-1 text-[9px] font-black uppercase py-2 rounded-lg bg-gray-900 text-gray-400 hover:text-white hover:bg-gray-800 transition-all border border-gray-800"
                            >
                                Show All
                            </button>
                            <button 
                                onClick={() => { setSelectedExchanges([]); setPage(1); }}
                                className="flex-1 text-[9px] font-black uppercase py-2 rounded-lg bg-gray-900 text-gray-400 hover:text-white hover:bg-gray-800 transition-all border border-gray-800"
                            >
                                Hide All
                            </button>
                        </div>
                        <div className="max-h-64 overflow-y-auto p-2 custom-scrollbar">
                            {ALL_EXCHANGES.map(ex => {
                                const isSelected = selectedExchanges.includes(ex);
                                return (
                                    <button 
                                        key={ex} 
                                        onClick={() => { setSelectedExchanges(prev => isSelected ? prev.filter(e => e !== ex) : [...prev, ex]); setPage(1); }}
                                        className={`w-full flex items-center justify-between px-4 py-2.5 rounded-xl transition-all mb-1 ${isSelected ? 'bg-blue-600/5 text-white' : 'hover:bg-white/5 text-gray-500'}`}
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className={`w-4 h-4 rounded-md border flex items-center justify-center transition-all ${isSelected ? 'bg-blue-600 border-blue-400' : 'border-gray-800'}`}>
                                                {isSelected && <CheckSquare size={10} className="text-white" />}
                                            </div>
                                            <span className="text-[10px] font-black uppercase tracking-widest">{ex}</span>
                                        </div>
                                        <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: EXCHANGE_COLORS[ex] }}></div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>
            
            <div className="flex items-center gap-4 bg-[#080808] px-4 py-2 rounded-xl border border-gray-900">
                <span className="text-[9px] font-black text-gray-600 uppercase tracking-widest">Global Aggregation</span>
                <Activity size={14} className="text-blue-500 animate-pulse" />
            </div>
        </div>

        {viewMode === 'matrix' && (
        <div className="bg-[#0a0a0a] rounded-2xl border border-gray-900 overflow-hidden shadow-2xl">
            <div className="overflow-x-auto custom-scrollbar">
                <table className="w-full text-left border-collapse table-fixed min-w-[1000px]">
                    <thead>
                        <tr className="bg-[#0f0f0f] border-b border-gray-800 text-[10px] font-black text-gray-600 uppercase tracking-widest">
                            <th className="w-48 px-8 py-6 sticky left-0 bg-[#0f0f0f] z-30 cursor-pointer group" onClick={() => handleSort('symbol')}>
                                <div className="flex items-center gap-2">Symbol <ArrowUpDown size={12} className="group-hover:text-white transition-colors" /></div>
                            </th>
                            {selectedExchanges.map(ex => (
                                <th key={ex} className="px-2 py-6 text-center cursor-pointer border-l border-gray-900/50 hover:text-white transition-colors uppercase" onClick={() => handleSort(ex)}>{ex}</th>
                            ))}
                            <th className="w-40 px-6 py-6 text-center border-l border-gray-900/50 cursor-pointer group/max relative" onClick={() => handleSort(dataMode === 'price' ? 'maxPrice' : 'maxApr')}>
                                <div className="flex items-center justify-center gap-1.5">
                                    <span>{dataMode === 'price' ? 'Max Price' : 'Max APR'}</span>
                                    <div className="relative group/tip">
                                        <ShieldCheck size={12} className="text-blue-500 cursor-help" />
                                        <div className="absolute top-full right-0 mt-3 w-64 p-4 bg-[#0d0d0d] border border-gray-800 rounded-[20px] shadow-3xl opacity-0 group-hover/tip:opacity-100 pointer-events-none transition-all z-[9999] text-left ring-1 ring-white/5">
                                            <p className="text-[10px] font-black text-white uppercase mb-2">{dataMode === 'price' ? 'Highest Mark Price' : 'Single-Venue Max APR'}</p>
                                            <p className="text-[9px] text-gray-400 leading-relaxed mb-2">{dataMode === 'price' ? 'The highest mark price across all selected exchanges.' : 'The highest available annualized yield from any single selected exchange.'}</p>
                                            <div className="font-mono text-[8px] bg-black/50 p-2 rounded-lg border border-white/5 text-blue-400">{dataMode === 'price' ? 'Max price among selected venues' : 'APR = Rate × (24/Int) × 365'}</div>
                                            <div className="absolute bottom-full right-1 border-[6px] border-transparent border-b-[#0d0d0d]"></div>
                                        </div>
                                    </div>
                                </div>
                            </th>
                            <th className="w-40 px-6 py-6 text-center border-l border-gray-900/50 cursor-pointer group/spread relative" onClick={() => handleSort(dataMode === 'price' ? 'priceSpread' : 'spread')}>
                                <div className="flex items-center justify-center gap-1.5">
                                    <span>{dataMode === 'price' ? 'Price Gap' : 'Spread APR'}</span>
                                    <div className="relative group/tip">
                                        <Zap size={12} className="text-purple-500 cursor-help" />
                                        <div className="absolute top-full right-0 mt-3 w-64 p-4 bg-[#0d0d0d] border border-gray-800 rounded-[20px] shadow-3xl opacity-0 group-hover/tip:opacity-100 pointer-events-none transition-all z-[9999] text-left ring-1 ring-white/5">
                                            <p className="text-[10px] font-black text-white uppercase mb-2">{dataMode === 'funding' ? 'Arbitrage Gap' : 'Price Gap'}</p>
                                            <p className="text-[9px] text-gray-400 leading-relaxed mb-2">{dataMode === 'funding' ? 'Maximum delta-neutral potential between selected venues.' : 'Price difference between highest and lowest venue.'}</p>
                                            <div className="font-mono text-[8px] bg-black/50 p-2 rounded-lg border border-white/5 text-purple-400">{dataMode === 'funding' ? 'Spread = Max(APR) - Min(APR)' : 'Spread = Max Price - Min Price'}</div>
                                            <div className="absolute bottom-full right-1 border-[6px] border-transparent border-b-[#0d0d0d]"></div>
                                        </div>
                                    </div>
                                </div>
                            </th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-900">
                        {Object.keys(rates).length === 0 ? (
                            Array.from({ length: 5 }).map((_, i) => (
                                <tr key={i} className="animate-pulse">
                                    <td className="px-8 py-8"><div className="h-4 bg-gray-900 rounded w-24"></div></td>
                                    {selectedExchanges.map(ex => <td key={ex} className="px-2 py-8"><div className="h-4 bg-gray-900 rounded mx-auto w-12"></div></td>)}
                                    <td className="px-8 py-8"><div className="h-4 bg-gray-900 rounded mx-auto w-16"></div></td>
                                </tr>
                            ))
                        ) : currentSymbols.map(row => (
                            <tr key={row.symbol} className="hover:bg-blue-600/[0.03] transition-colors group">
                                <td className="px-8 py-5 sticky left-0 bg-[#0a0a0a] z-20 border-r border-gray-900 font-black text-white text-sm tracking-tighter cursor-pointer group" onClick={() => { setCompareSymbol(row.symbol); setTimeframe(7); }}>
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                          <button onClick={e => { e.stopPropagation(); toggleFav(row.symbol) }} className="text-gray-800 hover:text-yellow-500 transition-colors" title={favorites.includes(row.symbol) ? 'Remove from favorites' : 'Add to favorites'}>
                                            <Star size={12} className={favorites.includes(row.symbol) ? 'fill-yellow-500 text-yellow-500' : ''} />
                                          </button>
                                          <span>{row.base} <span className="text-[10px] text-gray-700 ml-1 font-bold">{row.quote}</span></span>
                                        </div>
                                        <ExternalLink size={12} className="text-gray-800 group-hover:text-blue-500 opacity-0 group-hover:opacity-100 transition-all" />
                                    </div>
                                </td>
                                {selectedExchanges.map(ex => {
                                    const rate = row.rates[ex];
                                    const interval = row.intervals[ex];
                                    const markPrice = row.markPrices?.[ex];

                                    const symInv = symbolInventory?.[ex];
                                    const isSupported = !symInv || symInv.includes(row.symbol);

                                    const showFunding = dataMode === 'funding' || dataMode === 'all';
                                    const showPrice = dataMode === 'price' || dataMode === 'all';
                                    const primaryVal = showFunding ? (rate || 0) * 100 : (markPrice || 0);
                                    const hasFunding = rate !== undefined;
                                    const hasPrice = markPrice !== undefined;
                                    const hasData = showFunding ? hasFunding : hasPrice;

                                    let opacity = 0;
                                    let style = { backgroundColor: 'transparent' };
                                    if (hasData) {
                                        if (showFunding) {
                                            opacity = Math.min(Math.abs(primaryVal) / 0.05, 1);
                                            style = { backgroundColor: primaryVal > 0 ? `rgba(16, 185, 129, ${0.1 + opacity * 0.7})` : `rgba(239, 68, 68, ${0.1 + opacity * 0.7})` };
                                        } else {
                                            opacity = Math.min(primaryVal / 100000, 1);
                                            style = { backgroundColor: `rgba(245, 158, 11, ${0.1 + opacity * 0.7})` };
                                        }
                                    }

                                    let healthColor = '#22c55e';
                                    if (rate !== undefined) {
                                        const redFlags = (Math.abs(rate) >= 0.01 ? 1 : 0) + (interval < 1 || interval > 24 ? 1 : 0) + (row.symbol.length < 3 ? 1 : 0);
                                        healthColor = redFlags === 0 ? '#22c55e' : redFlags === 1 ? '#eab308' : '#ef4444';
                                    }

                                    const handleClick = () => {
                                        if (rate !== undefined) {
                                            setSelectedPair({exchange: ex, symbol: row.symbol});
                                            setTimeframe(7);
                                        }
                                    };

                                    const displayText = hasData
                                        ? (showFunding ? `${(rate! * 100).toFixed(4)}%` : formatPrice(Number(markPrice)))
                                        : (isSupported ? '--' : 'N/A');

                                    return (
                                        <td key={ex} className="p-0 border-l border-gray-900/20">
                                            <div style={style} className="w-full h-[76px] flex flex-col items-center justify-center cursor-pointer hover:brightness-150 transition-all border-b border-transparent hover:border-white/20 relative group/cell" onClick={handleClick}>
                                                {showFunding && rate !== undefined && <div className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full" style={{ backgroundColor: healthColor }} title={healthColor === '#22c55e' ? 'Valid' : healthColor === '#eab308' ? 'Warning' : 'Suspicious'} />}
                                                <span className={`font-mono text-[11px] font-bold ${hasData ? 'text-white' : (isSupported ? 'text-gray-800/50' : 'text-gray-800/30')}`}>
                                                    {displayText}
                                                </span>
                                                {dataMode === 'all' && rate !== undefined && (
                                                    <span className="text-[8px] font-mono text-white/40 mt-0.5">{markPrice ? formatPrice(Number(markPrice)) : ''}</span>
                                                )}
                                                {dataMode === 'all' && markPrice !== undefined && rate === undefined && (
                                                    <span className="text-[8px] font-mono text-white/40 mt-0.5">{rate !== undefined ? `${(rate * 100).toFixed(4)}%` : ''}</span>
                                                )}
                                                {rate !== undefined && (
                                                    <span className="text-[8px] font-black opacity-40 text-white uppercase mt-0.5">{showFunding ? `${interval}H` : `${interval}H`}</span>
                                                )}
                                            </div>
                                        </td>
                                    );
                                })}
                                <td className="px-6 py-5 text-center border-l border-gray-900 font-black text-xs text-blue-500">
                                    {dataMode === 'price' ? (row.maxPrice > 0 ? formatPrice(row.maxPrice) : '--') : (row.maxApr > 0 ? `${row.maxApr.toFixed(1)}%` : '--')}
                                </td>
                                <td className="px-6 py-5 text-center border-l border-gray-900 font-black text-xs text-purple-500">
                                    {dataMode === 'price' ? (row.priceSpread > 0 ? formatPrice(row.priceSpread) : '--') : (row.spread > 0 ? `${row.spread.toFixed(1)}%` : '--')}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className="bg-[#0f0f0f] border-t border-gray-900 px-8 py-4 flex justify-between items-center text-[10px] font-black text-gray-700 uppercase tracking-widest">
                <div className="flex gap-4 items-center">
                    <span>{filteredData.length} Assets Loaded</span>
                    <div className="flex gap-2">
                        {[25, 50, 100].map(s => <button key={s} onClick={() => {setPageSize(s); setPage(1);}} className={pageSize === s ? 'text-white underline' : 'hover:text-gray-500'}>{s}</button>)}
                    </div>
                </div>
                <div className="flex gap-4 items-center">
                    <button onClick={() => setPage(p => Math.max(1, p-1))} className="hover:text-white transition-colors"><ChevronLeft size={16}/></button>
                    <span className="text-gray-500">Page <span className="text-white">{page}</span> / {totalPages}</span>
                    <button onClick={() => setPage(p => Math.min(totalPages, p+1))} className="hover:text-white transition-colors"><ChevronRight size={16}/></button>
                </div>
            </div>
        </div>
        )}
        {viewMode === 'heatplot' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                {currentSymbols.map(row => (
                    <div key={row.symbol} className="bg-[#080808] border border-gray-900 rounded-2xl p-4 hover:border-blue-900/50 transition-all group overflow-hidden relative">
                        <div className="flex justify-between items-center mb-4">
                            <h4 className="text-sm font-black text-white italic">{row.symbol}</h4>
                            <button onClick={() => setCompareSymbol(row.symbol)} className="text-[8px] font-black uppercase text-blue-500 hover:text-white">Compare</button>
                        </div>
                        <div className="grid grid-cols-3 gap-1">
                            {selectedExchanges.map(ex => {
                                const rate = row.rates[ex];
                                const markPrice = row.markPrices?.[ex];
                                const showFunding = dataMode === 'funding' || dataMode === 'all';
                                const showPrice = dataMode === 'price' || dataMode === 'all';
                                const displayVal = showFunding ? (rate || 0) * 100 : (markPrice || 0);
                                const hasData = showFunding ? rate !== undefined : markPrice !== undefined;

                                let color = '#111';
                                if (hasData) {
                                    if (showFunding) {
                                        const opacity = Math.min(Math.abs(displayVal) / 0.05, 1);
                                        color = displayVal > 0 ? `rgba(16, 185, 129, ${0.2 + opacity * 0.8})` : `rgba(239, 68, 68, ${0.2 + opacity * 0.8})`;
                                    } else {
                                        const opacity = Math.min(displayVal / 100000, 1);
                                        color = `rgba(245, 158, 11, ${0.2 + opacity * 0.8})`;
                                    }
                                }
                                return (
                                    <div 
                                        key={ex} 
                                        title={showFunding
                                            ? `${ex.toUpperCase()}: ${rate !== undefined ? (rate*100).toFixed(4)+'%' : 'N/A'}${markPrice ? ' | '+formatPrice(Number(markPrice)) : ''}`
                                            : `${ex.toUpperCase()}: ${markPrice !== undefined ? formatPrice(Number(markPrice)) : 'N/A'}`
                                        }
                                        className="h-8 rounded-sm relative group/cell cursor-pointer"
                                        style={{ backgroundColor: color }}
                                        onClick={() => rate !== undefined && setSelectedPair({exchange: ex, symbol: row.symbol})}
                                    >
                                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover/cell:opacity-100 transition-opacity">
                                            <span className="text-[6px] font-black text-white uppercase opacity-80">{showFunding ? ex.substring(0,3) : (markPrice ? '$'+Number(markPrice).toLocaleString(undefined,{maximumFractionDigits:0}) : '--')}</span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                        <div className="mt-3 pt-3 border-t border-gray-900/50 flex justify-between items-center">
                             <div className="text-[8px] font-bold text-gray-600 uppercase">{dataMode === 'price' ? 'Price Gap' : 'Spread APR'}</div>
                             <div className="text-[10px] font-black text-purple-500">{dataMode === 'price' ? (row.priceSpread > 0 ? formatPrice(row.priceSpread) : '--') : (row.spread > 0 ? `${row.spread.toFixed(1)}%` : '--')}</div>
                        </div>
                    </div>
                ))}
            </div>
        )}
        {viewMode === 'calc' && (
            <ArbitrageCalculator rates={rates} />
        )}
        {viewMode === 'watch' && (
        <div className="bg-[#0a0a0a] rounded-2xl border border-gray-900 overflow-hidden shadow-2xl">
            {favorites.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                    <Star size={40} className="text-gray-800 mb-4" />
                    <p className="text-[10px] font-black text-gray-700 uppercase tracking-widest mb-1">No Watched Symbols</p>
                    <p className="text-[9px] text-gray-800 font-bold uppercase tracking-wider">Click the ⭐ star icon next to any symbol to add it here</p>
                </div>
            ) : (
                <div>
                    <div className="px-8 py-4 border-b border-gray-900 flex items-center justify-between">
                        <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest">Watched Symbols ({favorites.length})</div>
                    </div>
                    <div className="overflow-x-auto custom-scrollbar">
                        <table className="w-full text-left border-collapse table-fixed min-w-[800px]">
                            <thead>
                                <tr className="bg-[#0f0f0f] border-b border-gray-800 text-[10px] font-black text-gray-600 uppercase tracking-widest">
                                    <th className="w-48 px-8 py-6">Symbol</th>
                                    {selectedExchanges.map(ex => (
                                        <th key={ex} className="px-2 py-6 text-center border-l border-gray-900/50 uppercase">{ex}</th>
                                    ))}
                                    <th className="w-24 px-4 py-6 text-center border-l border-gray-900/50">Action</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-900">
                                {filteredData.filter(r => favorites.includes(r.symbol)).map(row => (
                                    <tr key={row.symbol} className="hover:bg-blue-600/[0.03] transition-colors">
                                        <td className="px-8 py-4 sticky left-0 bg-[#0a0a0a] z-20 border-r border-gray-900 font-black text-white text-sm tracking-tighter">
                                            <div className="flex items-center gap-2">
                                                <span>{row.base} <span className="text-[10px] text-gray-700 font-bold">{row.quote}</span></span>
                                            </div>
                                        </td>
                                        {selectedExchanges.map(ex => {
                                            const rate = row.rates[ex];
                                            const val = (rate || 0) * 100;
                                            const opacity = Math.min(Math.abs(val) / 0.05, 1);
                                            const bg = rate === undefined ? 'transparent' : (val > 0 ? `rgba(16, 185, 129, ${0.1 + opacity * 0.7})` : `rgba(239, 68, 68, ${0.1 + opacity * 0.7})`);
                                            return (
                                                <td key={ex} className="p-0 border-l border-gray-900/20">
                                                    <div style={{ backgroundColor: bg }} className="w-full h-14 flex items-center justify-center cursor-pointer hover:brightness-150 transition-all" onClick={() => { if (rate !== undefined) { setSelectedPair({exchange: ex, symbol: row.symbol}); setTimeframe(7); }}}>
                                                        <span className={`font-mono text-[11px] font-bold ${rate !== undefined ? 'text-white' : 'text-gray-800/50'}`}>{rate !== undefined ? `${val.toFixed(4)}%` : '--'}</span>
                                                    </div>
                                                </td>
                                            );
                                        })}
                                        <td className="px-4 py-4 text-center border-l border-gray-900/20">
                                            <button onClick={() => toggleFav(row.symbol)} className="text-gray-600 hover:text-yellow-500 transition-colors" title="Remove from watchlist">
                                                <Star size={14} className="fill-yellow-500 text-yellow-500" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
        )}

        {compareSymbol && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/95 backdrop-blur-md animate-in fade-in duration-300">
                <div className="bg-[#080808] border border-gray-800 w-full max-w-6xl rounded-[40px] shadow-3xl overflow-hidden relative">
                    <div className="h-2 bg-gradient-to-r from-blue-600 via-purple-600 to-red-600"></div>
                    <button onClick={() => setCompareSymbol(null)} className="absolute right-8 top-8 text-gray-500 hover:text-white bg-[#111] p-3 rounded-full border border-gray-800 transition-all z-50">
                        <X size={24}/>
                    </button>
                    <div className="p-12">
                        <div className="flex items-end justify-between gap-6 mb-12">
                            <div className="flex items-end gap-6">
                                <div className="w-20 h-20 bg-white/5 rounded-3xl flex items-center justify-center border border-white/10 shadow-inner"><Globe size={40} className="text-blue-500" /></div>
                                <div>
                                    <h2 className="text-6xl font-black text-white italic tracking-tighter uppercase leading-none mb-2">{compareSymbol}</h2>
                                    <p className="text-xs font-black text-gray-600 uppercase tracking-[0.5em]">Cross-Exchange Comparative History</p>
                                </div>
                            </div>
                            <div className="text-right flex flex-col items-end gap-3">
                                <div className="flex gap-4 items-center">
                                    <div className="flex flex-col items-end">
                                        <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1">Timeframe</div>
                                        <TimeframeSelector />
                                    </div>
                                    <div className="flex flex-col items-end">
                                        <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1">Visibility</div>
                                        <div className="flex gap-2">
                                            <button onClick={() => setVisibleExchanges(ALL_EXCHANGES)} className="text-[9px] bg-[#111] px-3 py-1 rounded-full border border-gray-800 hover:text-white uppercase font-bold">Show All</button>
                                            <button onClick={() => setVisibleExchanges([])} className="text-[9px] bg-[#111] px-3 py-1 rounded-full border border-gray-800 hover:text-white uppercase font-bold">Hide All</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div className="bg-[#040404] rounded-[32px] p-8 border border-gray-900 shadow-inner min-h-[500px] flex items-center justify-center relative">
                            {loadingMulti && Object.keys(multiHistory || {}).length === 0 ? (
                                <div className="flex flex-col items-center gap-4">
                                    <LoadingSpinner label="Fetching exchange history data..." />
                                </div>
                            ) : multiHistory && Object.keys(multiHistory).length > 0 ? (
                                <TVChart key={`cmp-${compareSymbol}`} data={multiHistory} isCompare={true} visibleExchanges={visibleExchanges} />
                            ) : !loadingMulti ? (
                                <div className="text-gray-800 font-black uppercase text-[10px] tracking-widest">No historical data available</div>
                            ) : null}
                        </div>

                        <div className="mt-8 flex flex-wrap justify-center gap-4">
                            {multiHistory && Object.keys(multiHistory).length > 0 ? (
                                Object.keys(multiHistory).map(ex => {
                                    const isVisible = visibleExchanges.includes(ex);
                                    const hasData = multiHistory[ex]?.length > 0;
                                    return (
                                        <button 
                                            key={ex} 
                                            onClick={() => toggleExchangeVisibility(ex)}
                                            className={`flex items-center gap-3 px-4 py-2 rounded-2xl border transition-all ${isVisible ? 'bg-white/[0.03] border-gray-800 opacity-100 shadow-lg' : 'border-transparent opacity-20 grayscale'}`}
                                            title={`${multiHistory[ex]?.length || 0} data points`}
                                        >
                                            <div className="w-4 h-4 rounded-full flex items-center justify-center" style={{ backgroundColor: EXCHANGE_COLORS[ex] }}>
                                                {isVisible ? <Eye size={8} className="text-black" /> : <EyeOff size={8} className="text-black" />}
                                            </div>
                                            <span className="text-[11px] font-black uppercase tracking-widest flex items-center gap-1.5" style={{ color: isVisible ? '#fff' : '#888' }}>
                                                {ex}
                                                {hasData && <span className="text-[7px] text-green-600 font-bold">✓</span>}
                                            </span>
                                        </button>
                                    );
                                })
                            ) : !loadingMulti ? (
                                <div className="text-gray-600 text-[10px] font-black uppercase tracking-widest">No exchanges have historical data for this pair</div>
                            ) : null}
                        </div>
                    </div>
                </div>
            </div>
        )}
      </main>

      {isAlertPanelOpen && (
        <AlertPanel
          rules={rules}
          events={events}
          soundEnabled={soundEnabled}
          onAddRule={addRule}
          onRemoveRule={removeRule}
          onToggleRule={toggleRule}
          onToggleSound={toggleSound}
          onClose={() => setIsAlertPanelOpen(false)}
        />
      )}
      <ToastContainer events={events} activeToastIds={activeToastIds} onDismiss={dismissToast} />
    </div>
  );
}

export default App;
