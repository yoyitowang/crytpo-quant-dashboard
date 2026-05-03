import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Search, BarChart3, ArrowUpDown, ChevronLeft, ChevronRight, Zap, Grid, LayoutGrid, Clock, Filter, CheckSquare, Square, TrendingUp, TrendingDown, Layers, Activity, Globe, ShieldCheck, AlertTriangle, Monitor, ExternalLink, X } from 'lucide-react';
import { createChart, ColorType, IChartApi, ISeriesApi } from 'lightweight-charts';

interface FundingRate {
  exchange: string;
  symbol: string;
  rate: number;
  settlement_time?: string;
  timestamp: string;
}

const EXCHANGE_COLORS: Record<string, string> = {
    'binance': '#F3BA2F', 'okx': '#FFFFFF', 'bybit': '#FFB11A', 'bitget': '#00F0FF',
    'gate': '#E02A44', 'kucoin': '#24AE8F', 'coinw': '#3B82F6', 'mexc': '#0081FF', 'bingx': '#3182CE'
};

const ALL_EXCHANGES = ['binance', 'okx', 'bybit', 'bitget', 'gate', 'kucoin', 'coinw', 'mexc', 'bingx'];

// --- TradingView 專業圖表組件 ---
const TVChart = ({ data, colors, isCompare = false }: { data: any, colors?: string[], isCompare?: boolean }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);

    useEffect(() => {
        if (!containerRef.current) return;

        const chart = createChart(containerRef.current, {
            layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#888' },
            grid: { vertLines: { color: '#111' }, horzLines: { color: '#111' } },
            width: containerRef.current.clientWidth,
            height: isCompare ? 500 : 350,
            timeScale: { borderColor: '#222', timeVisible: true, secondsVisible: false },
        });

        if (isCompare) {
            // 多交易所比對模式 (Line Series)
            Object.keys(data).forEach((ex, idx) => {
                const lineSeries = chart.addLineSeries({
                    color: EXCHANGE_COLORS[ex] || '#888',
                    lineWidth: 2,
                    title: ex.toUpperCase(),
                });
                // 將後端時間戳轉換為秒，並確保排序
                const sorted = data[ex].sort((a:any, b:any) => a.time - b.time);
                lineSeries.setData(sorted);
            });
        } else {
            // 單交易所模式 (Baseline Series: 專業綠紅區分)
            const baselineSeries = chart.addBaselineSeries({
                baseValue: { type: 'price', value: 0 },
                topLineColor: '#10b981', // 綠色 (正值)
                topFillColor1: 'rgba(16, 185, 129, 0.4)',
                topFillColor2: 'rgba(16, 185, 129, 0.05)',
                bottomLineColor: '#ef4444', // 紅色 (負值)
                bottomFillColor1: 'rgba(239, 68, 68, 0.05)',
                bottomFillColor2: 'rgba(239, 68, 68, 0.4)',
                lineWidth: 3,
                priceFormat: { type: 'percent', precision: 5, minMove: 0.00001 }
            });

            const sorted = [...data].sort((a: any, b: any) => {
                const t1 = new Date(a.timestamp).getTime() / 1000;
                const t2 = new Date(b.timestamp).getTime() / 1000;
                return t1 - t2;
            }).map(d => ({ time: new Date(d.timestamp).getTime() / 1000 as any, value: d.rate }));
            
            baselineSeries.setData(sorted);
        }

        chart.timeScale().fitContent();
        chartRef.current = chart;

        const handleResize = () => { if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth }); };
        window.addEventListener('resize', handleResize);
        return () => { window.removeEventListener('resize', handleResize); chart.remove(); };
    }, [data, isCompare]);

    return <div ref={containerRef} className="w-full" />;
};

function App() {
  const [rates, setRates] = useState<Record<string, FundingRate>>({});
  const [summary, setSummary] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [multiHistory, setMultiHistory] = useState<any>(null);
  const [selectedPair, setSelectedPair] = useState<{exchange: string, symbol: string} | null>(null);
  const [compareSymbol, setCompareSymbol] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
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

  const connectWebSocket = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => setConnected(true);
    ws.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            const items = Array.isArray(data) ? data : [data];
            setRates(prev => {
                const next = {...prev};
                items.forEach(i => { if(i?.exchange && i?.symbol) next[`${i.exchange}:${i.symbol}`] = i; });
                return next;
            });
        } catch {}
    };
    ws.onclose = () => { setConnected(false); setTimeout(connectWebSocket, 3000); };
    return ws;
  }, []);

  useEffect(() => { const ws = connectWebSocket(); return () => ws.close(); }, [connectWebSocket]);

  useEffect(() => {
    const fetchData = async () => {
        fetch('/api/analysis/summary').then(res => res.json()).then(setSummary);
        fetch('/api/health').then(res => res.json()).then(setHealth);
    };
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  // 獲取歷史
  useEffect(() => {
    if (selectedPair) {
        fetch(`/api/rates/history/${selectedPair.exchange}/${selectedPair.symbol}`)
            .then(res => res.json())
            .then(data => setHistory(Array.isArray(data) ? data : []));
    }
  }, [selectedPair]);

  // 獲取聚合歷史 (Modal)
  useEffect(() => {
    if (compareSymbol) {
        fetch(`/api/rates/history_all/${compareSymbol}`)
            .then(res => res.json())
            .then(setMultiHistory);
    } else { setMultiHistory(null); }
  }, [compareSymbol]);

  const filteredData = useMemo(() => {
    const symbolsMap: Record<string, Record<string, number>> = {};
    Object.values(rates).forEach(r => {
        if (!symbolsMap[r.symbol]) symbolsMap[r.symbol] = {};
        symbolsMap[r.symbol][r.exchange] = r.rate;
    });

    let result = Object.keys(symbolsMap).map(sym => {
        const activeRates = Object.entries(symbolsMap[sym]).filter(([ex]) => selectedExchanges.includes(ex)).map(([_, r]) => r * 1095);
        const spread = activeRates.length > 1 ? (Math.max(...activeRates) - Math.min(...activeRates)) : 0;
        return { symbol: sym, rates: symbolsMap[sym], spread, base: sym.replace(/USDT|USDC/i, ''), quote: sym.includes('USDC') ? 'USDC' : 'USDT' };
    });

    if (search) result = result.filter(r => r.symbol.toLowerCase().includes(search.toLowerCase()));
    result.sort((a, b) => {
        let v1: any, v2: any;
        if (sortConfig.key === 'symbol') { v1 = a.symbol; v2 = b.symbol; }
        else if (sortConfig.key === 'spread') { v1 = a.spread > 0 ? a.spread : undefined; v2 = b.spread > 0 ? b.spread : undefined; }
        else { v1 = a.rates[sortConfig.key]; v2 = b.rates[sortConfig.key]; }
        if (v1 === undefined) return 1; if (v2 === undefined) return -1;
        const res = v1 > v2 ? 1 : -1;
        return sortConfig.direction === 'asc' ? res : -res;
    });
    return result;
  }, [rates, search, selectedExchanges, sortConfig]);

  const currentSymbols = filteredData.slice((page - 1) * pageSize, page * pageSize);
  const totalPages = Math.max(1, Math.ceil(filteredData.length / pageSize));

  return (
    <div className="min-h-screen bg-[#000] text-gray-400 font-sans selection:bg-blue-500/30">
      <nav className="bg-[#080808] border-b border-gray-900 sticky top-0 z-50 px-6 py-3 flex flex-wrap justify-between items-center gap-4 shadow-2xl">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <Zap size={22} className="text-blue-500 fill-blue-500" />
            <h1 className="text-xl font-black text-white italic tracking-tighter uppercase">QuantMatrix v11.5</h1>
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
        {/* 1. 頂部統計 */}
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
                <div className="space-y-1.5">{summary?.top_positive?.map((r:any, i:number) => (
                    <div key={i} className="flex justify-between items-center text-[11px]">
                        <span className="font-bold text-gray-300 font-mono">{r.symbol} <span className="text-[8px] bg-blue-900/30 text-blue-400 px-1 rounded ml-1">{r.exchange}</span></span>
                        <span className="font-black text-green-400">{(r.rate * 100).toFixed(4)}%</span>
                    </div>
                ))}</div>
            </div>
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-3 flex items-center gap-2"><TrendingDown size={12} className="text-red-500"/> Top Receivers</div>
                <div className="space-y-1.5">{summary?.top_negative?.map((r:any, i:number) => (
                    <div key={i} className="flex justify-between items-center text-[11px]">
                        <span className="font-bold text-gray-300 font-mono">{r.symbol} <span className="text-[8px] bg-red-900/30 text-red-400 px-1 rounded ml-1">{r.exchange}</span></span>
                        <span className="font-black text-red-400">{(r.rate * 100).toFixed(4)}%</span>
                    </div>
                ))}</div>
            </div>
            <div className="bg-[#0a0a0a] border border-gray-900 rounded-2xl p-5 shadow-lg flex flex-col justify-center">
                <div className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1 flex items-center gap-2"><ShieldCheck size={14} className="text-blue-500"/> System Core</div>
                <div className="text-3xl font-black text-white">{filteredData.length}</div>
                <div className="text-[9px] font-bold text-gray-700 uppercase tracking-tighter">Monitoring {Object.keys(rates).length} Active Channels</div>
            </div>
        </div>

        {/* 2. 歷史圖表 (移動到這裡：統計下方) */}
        {selectedPair && history.length > 0 && (
            <div className="mb-8 animate-in zoom-in-95 duration-500">
                <div className="bg-[#080808] border border-blue-900/30 rounded-3xl p-6 shadow-2xl relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-0.5 bg-blue-600/50"></div>
                    <div className="flex justify-between items-center mb-6">
                        <div className="flex items-center gap-4">
                            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white"><BarChart3 size={20} /></div>
                            <div>
                                <h3 className="text-xl font-black text-white uppercase italic tracking-tighter">{selectedPair.symbol} <span className="text-blue-500 text-sm">{selectedPair.exchange}</span></h3>
                                <p className="text-[9px] font-bold text-gray-600 uppercase tracking-[0.2em]">Institutional Historical Analysis</p>
                            </div>
                        </div>
                        <button onClick={() => setSelectedPair(null)} className="text-gray-600 hover:text-white transition-colors"><X size={20}/></button>
                    </div>
                    <div className="h-[350px] w-full">
                        <TVChart data={history} />
                    </div>
                </div>
            </div>
        )}

        {/* 3. 交易所選擇 */}
        <div className="flex flex-wrap items-center gap-3 mb-6 bg-[#080808] p-3 rounded-xl border border-gray-900">
            {ALL_EXCHANGES.map(ex => (
                <button key={ex} onClick={() => { setSelectedExchanges(prev => prev.includes(ex) ? prev.filter(e => e !== ex) : [...prev, ex]); setPage(1); }} className={`text-[10px] font-black uppercase flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${selectedExchanges.includes(ex) ? 'bg-blue-600/10 text-blue-400 border border-blue-900/30' : 'text-gray-700 border border-transparent'}`}>
                    {selectedExchanges.includes(ex) ? <CheckSquare size={12}/> : <Square size={12}/>} {ex}
                </button>
            ))}
        </div>

        {/* 4. 矩陣表格 */}
        <div className="bg-[#0a0a0a] rounded-2xl border border-gray-900 overflow-hidden shadow-2xl">
            <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse table-fixed min-w-[1200px]">
                    <thead>
                        <tr className="bg-[#0f0f0f] border-b border-gray-800 text-[10px] font-black text-gray-600 uppercase tracking-widest">
                            <th className="w-48 px-8 py-6 sticky left-0 bg-[#0f0f0f] z-30 cursor-pointer group" onClick={() => handleSort('symbol')}>
                                <div className="flex items-center gap-2">Symbol <ArrowUpDown size={12} className="group-hover:text-white transition-colors" /></div>
                            </th>
                            {selectedExchanges.map(ex => (
                                <th key={ex} className="px-2 py-6 text-center cursor-pointer border-l border-gray-900/50 hover:text-white transition-colors uppercase" onClick={() => handleSort(ex)}>{ex}</th>
                            ))}
                            <th className="w-44 px-8 py-6 text-center border-l border-gray-900/50 cursor-pointer" onClick={() => handleSort('spread')}>Spread APR</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-900">
                        {currentSymbols.map(row => (
                            <tr key={row.symbol} className="hover:bg-blue-600/[0.03] transition-colors group">
                                <td className="px-8 py-5 sticky left-0 bg-[#0a0a0a] z-20 border-r border-gray-900 font-black text-white text-sm tracking-tighter cursor-pointer group" onClick={() => setCompareSymbol(row.symbol)}>
                                    <div className="flex items-center justify-between">
                                        <span>{row.base} <span className="text-[10px] text-gray-700 ml-1 font-bold">{row.quote}</span></span>
                                        <ExternalLink size={12} className="text-gray-800 group-hover:text-blue-500 opacity-0 group-hover:opacity-100 transition-all" />
                                    </div>
                                </td>
                                {selectedExchanges.map(ex => {
                                    const rate = row.rates[ex];
                                    const val = (rate || 0) * 100;
                                    const opacity = Math.min(Math.abs(val) / 0.05, 1);
                                    const style = rate === undefined ? { backgroundColor: 'transparent' } : { backgroundColor: val > 0 ? `rgba(16, 185, 129, ${0.1 + opacity * 0.7})` : `rgba(239, 68, 68, ${0.1 + opacity * 0.7})` };
                                    return (
                                        <td key={ex} className="p-0 border-l border-gray-900/20">
                                            <div style={style} className="w-full h-16 flex items-center justify-center cursor-pointer hover:brightness-150 transition-all border-b border-transparent hover:border-white/20" onClick={() => rate !== undefined && setSelectedPair({exchange: ex, symbol: row.symbol})}>
                                                <span className={`font-mono text-[11px] font-bold ${rate !== undefined ? 'text-white' : 'text-gray-800/50'}`}>{rate !== undefined ? `${(rate * 100).toFixed(4)}%` : '--'}</span>
                                            </div>
                                        </td>
                                    );
                                })}
                                <td className="px-8 py-5 text-center border-l border-gray-900 font-black text-xs text-purple-500">
                                    {row.spread > 0 ? `${row.spread.toFixed(1)}%` : '--'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className="bg-[#0f0f0f] border-t border-gray-900 px-8 py-4 flex justify-between items-center text-[10px] font-black text-gray-700 uppercase tracking-widest">
                <div className="flex gap-4 items-center">
                    <span>{filteredData.length} Assets</span>
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

        {/* 5. 全平台比對 Modal */}
        {compareSymbol && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/90 backdrop-blur-sm animate-in fade-in duration-300">
                <div className="bg-[#080808] border border-gray-800 w-full max-w-6xl rounded-[40px] shadow-3xl overflow-hidden relative">
                    <div className="h-2 bg-gradient-to-r from-blue-600 via-purple-600 to-red-600"></div>
                    <button onClick={() => setCompareSymbol(null)} className="absolute right-8 top-8 text-gray-500 hover:text-white bg-[#111] p-3 rounded-full border border-gray-800 transition-all z-50">
                        <X size={24}/>
                    </button>
                    <div className="p-12">
                        <div className="flex items-end gap-6 mb-12">
                            <div className="w-20 h-20 bg-white/5 rounded-3xl flex items-center justify-center border border-white/10 shadow-inner"><Globe size={40} className="text-blue-500" /></div>
                            <div>
                                <h2 className="text-6xl font-black text-white italic tracking-tighter uppercase leading-none mb-2">{compareSymbol}</h2>
                                <p className="text-xs font-black text-gray-600 uppercase tracking-[0.5em]">Cross-Exchange Comparative History</p>
                            </div>
                        </div>
                        
                        <div className="bg-[#040404] rounded-[32px] p-8 border border-gray-900 shadow-inner min-h-[500px] flex items-center justify-center">
                            {multiHistory ? (
                                <TVChart data={multiHistory} isCompare={true} />
                            ) : (
                                <div className="flex flex-col items-center gap-4 text-gray-700 font-black uppercase tracking-widest animate-pulse">
                                    <Activity className="animate-spin text-blue-500" />
                                    Synthesizing Global Data...
                                </div>
                            )}
                        </div>

                        <div className="mt-8 flex flex-wrap justify-center gap-6">
                            {multiHistory && Object.keys(multiHistory).map(ex => (
                                <div key={ex} className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-gray-500">
                                    <div className="w-3 h-1 rounded-full" style={{ backgroundColor: EXCHANGE_COLORS[ex] }}></div>
                                    {ex}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        )}
      </main>
    </div>
  );
}

export default App;
