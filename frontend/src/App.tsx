import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Search, BarChart3, ArrowUpDown, ChevronLeft, ChevronRight, Zap, Grid, LayoutGrid, Clock, Filter, CheckSquare, Square, TrendingUp, TrendingDown, Layers, Activity, Globe, ShieldCheck, AlertTriangle, Monitor } from 'lucide-react';
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, AreaChart, Area } from 'recharts';

interface FundingRate {
  exchange: string;
  symbol: string;
  rate: number;
  settlement_time?: string;
  timestamp: string;
}

interface Summary {
    market_sentiment: string;
    avg_funding_rate: number;
    top_positive: FundingRate[];
    top_negative: FundingRate[];
    stablecoin_stats: { usdt_avg: number; usdc_avg: number; };
    total_symbols: number;
}

interface SystemHealth {
    status: string;
    last_update: string;
    active_exchanges: string[];
    symbols_tracked: number;
}

const ALL_EXCHANGES = ['binance', 'okx', 'bybit', 'bitget', 'gate', 'kucoin', 'coinw', 'mexc', 'bingx'];

function App() {
  const [rates, setRates] = useState<Record<string, FundingRate>>({});
  const [summary, setSummary] = useState<Summary | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [selectedPair, setSelectedPair] = useState<{exchange: string, symbol: string} | null>(null);
  const [connected, setConnected] = useState(false);
  
  // UI 控制
  const [viewMode, setViewMode] = useState<'matrix' | 'heatplot'>('matrix');
  const [search, setSearch] = useState('');
  const [selectedExchanges, setSelectedExchanges] = useState<string[]>(ALL_EXCHANGES);
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);
  const [sortConfig, setSortConfig] = useState<{key: string, direction: 'asc' | 'desc'}>({key: 'spread', direction: 'desc'});

  const formatLocalTime = (isoStr: string | undefined) => {
    if (!isoStr || isoStr === "None") return "--:--:--";
    try {
        const date = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z');
        return date.toLocaleString();
    } catch (e) { return isoStr; }
  };

  // --- WebSocket 數據處理器：核心修復版本 ---
  const connectWebSocket = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("Terminal: WS Handshake Success.");
        setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // 支援批次包與單筆數據
        const items = Array.isArray(data) ? data : [data];
        
        setRates((prev) => {
            const next = { ...prev };
            let hasChange = false;
            items.forEach(item => {
                // 確保數據格式正確
                if (item && item.exchange && item.symbol) {
                    const key = `${item.exchange}:${item.symbol}`;
                    next[key] = item;
                    hasChange = true;
                }
            });
            return hasChange ? next : prev;
        });
      } catch (e) { console.error("WS Parse Error", e); }
    };

    ws.onclose = () => { setConnected(false); setTimeout(connectWebSocket, 3000); };
    return ws;
  }, []);

  useEffect(() => {
    const ws = connectWebSocket();
    return () => ws.close();
  }, [connectWebSocket]);

  // 定期抓取摘要與健康檢查
  useEffect(() => {
    const fetchData = async () => {
        try {
            const sumRes = await fetch('/api/analysis/summary');
            if (sumRes.ok) setSummary(await sumRes.json());
            const healthRes = await fetch('/api/health');
            if (healthRes.ok) setHealth(await healthRes.json());
        } catch (e) { console.error("Dashboard sync error", e); }
    };
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  // 數據計算
  const filteredData = useMemo(() => {
    const symbolsMap: Record<string, Record<string, number>> = {};
    Object.values(rates).forEach(r => {
        if (!symbolsMap[r.symbol]) symbolsMap[r.symbol] = {};
        symbolsMap[r.symbol][r.exchange] = r.rate;
    });

    let result = Object.keys(symbolsMap).map(sym => {
        const activeRates = Object.entries(symbolsMap[sym])
            .filter(([ex]) => selectedExchanges.includes(ex))
            .map(([_, r]) => r * (24/8) * 365 * 100);
        const spread = activeRates.length > 1 ? (Math.max(...activeRates) - Math.min(...activeRates)) : 0;
        return { symbol: sym, rates: symbolsMap[sym], spread, base: sym.replace(/USDT|USDC/i, ''), quote: sym.includes('USDC') ? 'USDC' : 'USDT' };
    });

    if (search) result = result.filter(r => r.symbol.toLowerCase().includes(search.toLowerCase()));

    result.sort((a, b) => {
        let v1: any, v2: any;
        if (sortConfig.key === 'symbol') { v1 = a.symbol; v2 = b.symbol; }
        else if (sortConfig.key === 'spread') { v1 = a.spread > 0 ? a.spread : undefined; v2 = b.spread > 0 ? b.spread : undefined; }
        else { v1 = a.rates[sortConfig.key]; v2 = b.rates[sortConfig.key]; }
        if (v1 === undefined && v2 === undefined) return 0;
        if (v1 === undefined) return 1; if (v2 === undefined) return -1;
        const res = v1 > v2 ? 1 : -1;
        return sortConfig.direction === 'asc' ? res : -res;
    });
    return result;
  }, [rates, search, selectedExchanges, sortConfig]);

  const currentSymbols = filteredData.slice((page - 1) * pageSize, page * pageSize);
  const totalPages = Math.max(1, Math.ceil(filteredData.length / pageSize));

  useEffect(() => {
    if (!selectedPair) return;
    fetch(`/api/rates/history/${selectedPair.exchange}/${selectedPair.symbol}`)
      .then(res => res.json())
      .then(data => setHistory(Array.isArray(data) ? data : []));
  }, [selectedPair]);

  const getHeatColor = (rate: number | undefined) => {
    if (rate === undefined) return { backgroundColor: 'rgba(30, 30, 30, 0.2)', color: '#444' };
    const val = rate * 100;
    const opacity = Math.min(Math.abs(val) / 0.05, 1);
    const color = val > 0 ? `rgba(0, 200, 120, ${0.1 + opacity * 0.8})` : `rgba(240, 60, 80, ${0.1 + opacity * 0.8})`;
    return { backgroundColor: color, color: Math.abs(val) > 0.02 ? '#fff' : (val > 0 ? '#00ffaa' : '#ff7788') };
  };

  const handleSort = (key: string) => {
    setSortConfig(prev => ({ key, direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc' }));
    setPage(1);
  };

  return (
    <div className="min-h-screen bg-[#000] text-gray-400 font-sans">
      <nav className="bg-[#080808] border-b border-gray-900 sticky top-0 z-50 px-6 py-3 flex flex-wrap justify-between items-center gap-4 shadow-2xl">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <Zap size={22} className="text-blue-500 fill-blue-500" />
            <h1 className="text-xl font-black text-white italic tracking-tighter uppercase">QuantMatrix v11.8</h1>
          </div>
          <div className="flex bg-[#111] p-1 rounded-lg border border-gray-800">
             <button onClick={() => setViewMode('matrix')} className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase flex items-center gap-2 transition-all ${viewMode === 'matrix' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500'}`}><LayoutGrid size={14}/> Matrix</button>
             <button onClick={() => setViewMode('heatplot')} className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase flex items-center gap-2 transition-all ${viewMode === 'heatplot' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500'}`}><Grid size={14}/> Heatplot</button>
          </div>
        </div>
        <div className="flex items-center gap-6">
            <div className="flex flex-col items-end">
                <div className="text-[10px] font-black uppercase tracking-tighter"><span className="text-gray-600">Last Sync:</span> <span className="text-blue-500">{formatLocalTime(health?.last_update)}</span></div>
                <div className="flex items-center gap-2 mt-0.5"><div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} /><span className="text-[9px] font-bold text-gray-700 uppercase">Engine: {connected ? 'Online' : 'Offline'}</span></div>
            </div>
            <input type="text" placeholder="SEARCH ASSET..." className="bg-[#111] border border-gray-800 rounded-full px-6 py-1.5 text-xs focus:outline-none focus:border-blue-900 w-48 font-bold uppercase" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </nav>

      <main className="max-w-[1800px] mx-auto p-6">
        {/* 統計看板 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg relative group">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1">Market Sentiment</div>
                <div className={`text-2xl font-black italic tracking-tighter ${summary?.market_sentiment === 'Bullish' ? 'text-green-500' : 'text-red-500'}`}>{summary?.market_sentiment || 'NEUTRAL'}</div>
                <div className="flex items-center gap-2 mt-3">
                    <div className="flex-1 h-1.5 bg-gray-900 rounded-full overflow-hidden flex">
                        <div className="h-full bg-green-500" style={{ width: `${50 + (summary?.avg_funding_rate || 0) * 1000}%` }}></div>
                        <div className="h-full bg-red-500" style={{ width: `${50 - (summary?.avg_funding_rate || 0) * 1000}%` }}></div>
                    </div>
                </div>
            </div>
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-3 flex items-center gap-2"><TrendingUp size={12} className="text-green-500"/> Top Payers</div>
                <div className="space-y-1.5">{summary?.top_positive?.map((r, i) => (
                    <div key={i} className="flex justify-between items-center text-[11px]">
                        <span className="font-bold text-gray-300 font-mono">
                            {r.symbol} <span className="text-[8px] bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded ml-1 uppercase">{r.exchange}</span>
                        </span>
                        <span className="font-black text-green-400">{(r.rate * 100).toFixed(4)}%</span>
                    </div>
                ))}</div>
            </div>
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-3 flex items-center gap-2"><TrendingDown size={12} className="text-red-500"/> Top Receivers</div>
                <div className="space-y-1.5">{summary?.top_negative?.map((r, i) => (
                    <div key={i} className="flex justify-between items-center text-[11px]">
                        <span className="font-bold text-gray-300 font-mono">
                            {r.symbol} <span className="text-[8px] bg-red-900/30 text-red-400 px-1.5 py-0.5 rounded ml-1 uppercase">{r.exchange}</span>
                        </span>
                        <span className="font-black text-red-400">{(r.rate * 100).toFixed(4)}%</span>
                    </div>
                ))}</div>
            </div>
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg flex flex-col justify-center">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1 flex items-center gap-2"><ShieldCheck size={14} className="text-blue-500"/> Assets Loaded</div>
                <div className="text-3xl font-black text-white">{filteredData.length}</div>
                <div className="text-[9px] font-bold text-gray-700 uppercase tracking-tighter">Syncing {Object.keys(rates).length} Keys</div>
            </div>
        </div>

        {/* 交易所選擇 */}
        <div className="flex flex-wrap items-center gap-3 mb-6 bg-[#080808] p-3 rounded-xl border border-gray-900">
            {ALL_EXCHANGES.map(ex => (
                <button key={ex} onClick={() => { setSelectedExchanges(prev => prev.includes(ex) ? prev.filter(e => e !== ex) : [...prev, ex]); setPage(1); }} className={`text-[10px] font-black uppercase flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${selectedExchanges.includes(ex) ? 'bg-blue-600/10 text-blue-400 border border-blue-900/30' : 'text-gray-700 border border-transparent'}`}>
                    {selectedExchanges.includes(ex) ? <CheckSquare size={12}/> : <Square size={12}/>} {ex}
                </button>
            ))}
        </div>

        {/* 矩陣表格 */}
        {viewMode === 'matrix' ? (
          <div className="bg-[#0a0a0a] rounded-2xl border border-gray-900 overflow-hidden shadow-2xl">
            <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse table-fixed min-w-[1200px]">
                    <thead>
                        <tr className="bg-[#0f0f0f] border-b border-gray-800 text-[10px] font-black text-gray-600 uppercase tracking-widest">
                            <th className="w-48 px-8 py-6 sticky left-0 bg-[#0f0f0f] z-30 cursor-pointer" onClick={() => handleSort('symbol')}>Symbol <ArrowUpDown size={12}/></th>
                            {selectedExchanges.map(ex => (
                                <th key={ex} className="px-2 py-6 text-center cursor-pointer border-l border-gray-900/50" onClick={() => handleSort(ex)}>{ex}</th>
                            ))}
                            <th className="w-44 px-8 py-6 text-center border-l border-gray-900/50 cursor-pointer" onClick={() => handleSort('spread')}>Spread APR</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-900">
                        {currentSymbols.map(row => (
                            <tr key={row.symbol} className="hover:bg-blue-600/[0.03] transition-colors group">
                                <td className="px-8 py-5 sticky left-0 bg-[#0a0a0a] z-20 border-r border-gray-900 font-black text-white text-sm tracking-tighter">
                                    {row.base} <span className="text-[10px] text-gray-700 ml-1 font-bold">{row.quote}</span>
                                </td>
                                {selectedExchanges.map(ex => {
                                    const rate = row.rates[ex];
                                    const style = getHeatColor(rate);
                                    return (
                                        <td key={ex} className="p-0 border-l border-gray-900/20">
                                            <div style={style} className="w-full h-16 flex items-center justify-center cursor-pointer hover:brightness-125 transition-all" onClick={() => rate !== undefined && setSelectedPair({exchange: ex, symbol: row.symbol})}>
                                                <span className={`font-mono text-[11px] font-bold ${rate !== undefined ? 'text-white' : 'text-gray-800'}`}>{rate !== undefined ? `${(rate * 100).toFixed(4)}%` : '--'}</span>
                                            </div>
                                        </td>
                                    );
                                })}
                                <td className="px-8 py-5 text-center border-l border-gray-900 font-black text-xs text-purple-500">
                                    {row.spread > 0 ? `${row.spread.toFixed(1)}%` : '--'}
                                </td>
                            </tr>
                        ))}
                        {currentSymbols.length === 0 && (
                            <tr><td colSpan={selectedExchanges.length + 2} className="py-20 text-center text-gray-700 italic">Connecting to high-speed data stream...</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
            <div className="bg-[#0f0f0f] border-t border-gray-900 px-8 py-4 flex justify-between items-center text-[10px] font-black text-gray-700 uppercase tracking-widest">
                <div className="flex gap-4 items-center">
                    <span>{filteredData.length} Symbols</span>
                    <div className="flex gap-2">
                        {[10, 25, 50, 100].map(s => (
                            <button key={s} onClick={() => {setPageSize(s); setPage(1);}} className={pageSize === s ? 'text-white' : 'hover:text-gray-600'}>{s}</button>
                        ))}
                    </div>
                </div>
                <div className="flex gap-4 items-center">
                    <button onClick={() => setPage(p => Math.max(1, p-1))}><ChevronLeft size={16}/></button>
                    <span>Page {page} / {totalPages}</span>
                    <button onClick={() => setPage(p => Math.min(totalPages, p+1))}><ChevronRight size={16}/></button>
                </div>
            </div>
          </div>
        ) : (
          <div className="bg-[#0a0a0a] rounded-2xl border border-gray-900 p-8 shadow-3xl overflow-hidden overflow-x-auto">
             <div className="inline-grid gap-1" style={{ gridTemplateRows: `repeat(${selectedExchanges.length}, 44px)`, gridTemplateColumns: `110px repeat(${currentSymbols.length}, 56px)` }}>
                <div className="sticky left-0 bg-[#0a0a0a] z-40"></div>
                {currentSymbols.map(s => <div key={s.symbol} className="text-[9px] font-black text-gray-600 origin-bottom-left rotate-[-45deg] translate-y-6 truncate w-20">{s.symbol}</div>)}
                {selectedExchanges.map(ex => (
                    <>
                        <div key={`heat-${ex}`} className="sticky left-0 bg-[#0a0a0a] z-30 flex items-center px-3 border-r border-gray-800 text-[10px] font-black text-gray-400 uppercase">{ex}</div>
                        {currentSymbols.map(s => (
                            <div key={`${ex}-${s.symbol}`} style={getHeatColor(s.rates[ex])} className="w-full h-full border border-black/20 hover:border-white/20 cursor-crosshair" onClick={() => s.rates[ex] !== undefined && setSelectedPair({exchange: ex, symbol: s.symbol})} />
                        ))}
                    </>
                ))}
             </div>
          </div>
        )}
        
        {/* 圖表終端機 */}
        {selectedPair && (
          <div className="mt-12 animate-in slide-in-from-bottom-12 duration-700">
             <div className="bg-[#080808] rounded-[40px] border border-gray-800 p-12 shadow-2xl relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-1 bg-blue-600 opacity-50"></div>
                <button onClick={() => setSelectedPair(null)} className="absolute right-12 top-12 text-gray-700 hover:text-white bg-[#111] p-4 rounded-full border border-gray-800 transition-all">✕</button>
                <div className="flex items-center gap-6 mb-12">
                    <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center shadow-2xl"><BarChart3 size={32} className="text-white" /></div>
                    <div>
                        <h2 className="text-4xl font-black text-white italic tracking-tighter uppercase leading-none mb-3">{selectedPair.symbol}</h2>
                        <span className="text-[10px] font-black text-blue-500 uppercase tracking-[0.4em] border border-blue-900/50 px-3 py-1 rounded-full">{selectedPair.exchange} Deep Terminal</span>
                    </div>
                </div>
                <div className="h-[500px] w-full bg-[#040404] rounded-3xl p-8 border border-gray-900">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={history} margin={{ top: 20, right: 0, left: 0, bottom: 0 }}>
                            <defs><linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563eb" stopOpacity={0.3}/><stop offset="95%" stopColor="#2563eb" stopOpacity={0}/></linearGradient></defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#111" vertical={false} />
                            <XAxis dataKey="timestamp" hide />
                            <YAxis stroke="#222" fontSize={10} tickFormatter={v => `${(v*100).toFixed(4)}%`} orientation="right" domain={['auto', 'auto']} />
                            <Tooltip contentStyle={{ backgroundColor: '#000', border: '1px solid #111', borderRadius: '12px' }} labelFormatter={l => formatLocalTime(l)} formatter={(val: any) => [`${(Number(val) * 100).toFixed(5)}%`, 'Rate']}/>
                            <Area type="stepAfter" dataKey="rate" stroke="#3b82f6" strokeWidth={5} fill="url(#colorArea)" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
             </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
