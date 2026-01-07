import { useState, useEffect } from 'react';
import Chart from 'react-apexcharts';
import {
    Brain,
    Clock,
    Users,
    AlertTriangle,
    RefreshCw,
    Target,
    Activity
} from 'lucide-react';
import type { ApexOptions } from 'apexcharts';

interface AnalyticsSummary {
    total_analyzed: number;
    total_execute: number;
    with_outcome: number;
    wins: number;
    losses: number;
    execute_rate: number;
    ai_agreement_rate: number;
    agreement_breakdown: {
        consensus: number;
        vision_vetoed: number;
        logic_vetoed: number;
    };
}

interface AIAnalytics {
    status: string;
    summary: AnalyticsSummary;
    confidence_distribution: {
        level: string;
        count: number;
    }[];
    recommendation_distribution: {
        recommendation: string;
        count: number;
        avg_confidence: number;
    }[];
    whale_signals: {
        signal: string;
        count: number;
        avg_confidence: number;
    }[];
    hourly_pattern: {
        hour: number;
        total: number;
        execute_count: number;
    }[];
    top_symbols: {
        symbol: string;
        count: number;
        avg_score: number;
        avg_confidence: number;
    }[];
}

export function MLAnalyticsPage() {
    const [analytics, setAnalytics] = useState<AIAnalytics | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const fetchAnalytics = async () => {
        try {
            setLoading(true);
            const response = await fetch('/api/ml/analytics');
            if (!response.ok) throw new Error('Failed to fetch analytics');
            const data = await response.json();
            setAnalytics(data);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAnalytics();
        const interval = setInterval(() => {
            fetch('/api/ml/analytics')
                .then(res => res.json())
                .then(data => setAnalytics(data))
                .catch(console.error);
        }, 60000);
        return () => clearInterval(interval);
    }, []);

    // ---------------------------------------------------------
    // CHART OPTIONS (Dark Mode / Tailwind Optimized)
    // ---------------------------------------------------------

    // 1. AI Agreement Donut
    const agreementOptions: ApexOptions = {
        chart: {
            type: 'donut',
            background: 'transparent',
            fontFamily: 'Inter, sans-serif',
        },
        labels: ['Consensus (Agreed)', 'Vision Vetoed', 'Logic Vetoed'],
        colors: ['#10b981', '#f59e0b', '#ef4444'], // Emerald, Amber, Red
        plotOptions: {
            pie: {
                donut: {
                    size: '70%',
                    labels: {
                        show: true,
                        name: { show: true, color: '#94a3b8' },
                        value: { show: true, color: '#e2e8f0', fontWeight: 'bold' },
                        total: {
                            show: true,
                            label: 'Agreed',
                            color: '#94a3b8',
                            formatter: () => `${analytics?.summary.ai_agreement_rate}%`
                        }
                    }
                }
            }
        },
        dataLabels: { enabled: false },
        stroke: { show: false },
        theme: { mode: 'dark' },
        legend: { position: 'bottom', labels: { colors: '#94a3b8' } }
    };

    const agreementSeries = analytics ? [
        analytics.summary.agreement_breakdown?.consensus || analytics.summary.total_execute, // Fallback if old API
        analytics.summary.agreement_breakdown?.vision_vetoed || 0,
        analytics.summary.agreement_breakdown?.logic_vetoed || 0
    ] : [0, 0, 0];

    // 2. Confidence Histogram
    const confidenceOptions: ApexOptions = {
        chart: {
            type: 'bar',
            toolbar: { show: false },
            background: 'transparent',
            fontFamily: 'Inter, sans-serif',
        },
        plotOptions: {
            bar: {
                borderRadius: 4,
                columnWidth: '60%',
                distributed: true, // Different colors per bar
            }
        },
        colors: ['#ef4444', '#f59e0b', '#10b981'], // Low (Red), Mid (Amber), High (Green)
        xaxis: {
            categories: analytics?.confidence_distribution.map(d => d.level) || [],
            labels: { style: { colors: '#94a3b8' } },
            axisBorder: { show: false },
            axisTicks: { show: false }
        },
        yaxis: {
            labels: { style: { colors: '#94a3b8' } }
        },
        grid: {
            borderColor: '#334155',
            strokeDashArray: 4,
        },
        tooltip: { theme: 'dark' },
        legend: { show: false }
    };

    const confidenceSeries = [{
        name: 'Signals',
        data: analytics?.confidence_distribution.map(d => d.count) || []
    }];

    // 3. Whale Sentiment (Bar)
    const whaleOptions: ApexOptions = {
        chart: {
            type: 'bar',
            toolbar: { show: false },
            background: 'transparent',
            fontFamily: 'Inter, sans-serif',
        },
        plotOptions: {
            bar: {
                horizontal: true,
                borderRadius: 4,
                distributed: true
            }
        },
        // Color mapping based on index (Hack: Assumes Order or map manually)
        // Better: Function in fill? Apexcharts is tricky with dynamic colors in simple series.
        // We'll rely on distributed: true and palette, or manually ordering data.
        colors: [
            '#ef4444', // Bearish / Dump
            '#10b981', // Bullish / Pump
            '#64748b'  // Neutral / Other
        ],
        xaxis: {
            labels: { style: { colors: '#94a3b8' } },
            axisBorder: { show: false }
        },
        yaxis: {
            labels: { style: { colors: '#94a3b8' } }
        },
        grid: {
            borderColor: '#334155',
            strokeDashArray: 4,
        },
        tooltip: { theme: 'dark' },
        legend: { show: false }
    };

    // Prepare whale data sorted (Bearish, Bullish)
    // We assume analytics includes them. Let's map properly.
    const whaleData = analytics ? analytics.whale_signals.map(w => ({
        x: w.signal,
        y: w.count,
        fillColor: w.signal.includes('DUMP') ? '#ef4444' : w.signal.includes('PUMP') ? '#10b981' : '#64748b'
    })) : [];

    const whaleSeries = [{
        name: 'Signals',
        data: whaleData
    }];


    // Calculate Precision for Custom Widget
    const precision = analytics && (analytics.summary.wins + analytics.summary.losses) > 0
        ? Math.round((analytics.summary.wins / (analytics.summary.wins + analytics.summary.losses)) * 100)
        : 0;

    return (
        <div className="space-y-6 animate-fade-in text-slate-800 dark:text-slate-100 pb-10">
            <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                <div>
                    <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-500 to-pink-600 flex items-center gap-3">
                        <Brain className="w-8 h-8 text-purple-500" />
                        Predictive AI
                    </h1>
                    <p className="text-slate-500 dark:text-slate-400 mt-1 text-sm">Real-time market logic and vision consensus engine</p>
                </div>
                <div className="flex gap-3">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                        <Clock className="w-3.5 h-3.5" />
                        <span>Last 7 Days</span>
                    </div>
                    <button
                        onClick={fetchAnalytics}
                        className="p-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700"
                        title="Refresh Data"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </header>

            {loading && !analytics ? (
                <div className="flex items-center justify-center h-96">
                    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500"></div>
                </div>
            ) : error ? (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 rounded-xl text-red-600 dark:text-red-400 flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5" />
                    {error}
                </div>
            ) : analytics ? (
                <div className="space-y-6">

                    {/* ROW 1: Accuracy & Agreement (Key Metrics) */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                        {/* 1. Accuracy Matrix (New Feature) */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm relative overflow-hidden group hover:border-emerald-500/50 transition-all">
                            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                                <Target className="w-24 h-24 text-emerald-500" />
                            </div>
                            <h3 className="text-lg font-bold mb-6 flex items-center gap-2 relative z-10">
                                <Target className="w-5 h-5 text-emerald-500" />
                                Prediction Accuracy
                            </h3>

                            <div className="flex items-center justify-between mb-8 relative z-10">
                                <div>
                                    <div className="text-4xl font-black text-slate-900 dark:text-white tracking-tight">
                                        {precision}%
                                    </div>
                                    <div className="text-xs font-bold text-emerald-500 uppercase tracking-widest mt-1">Precision Score</div>
                                </div>
                                <div className="text-right">
                                    <div className="text-sm text-slate-500 dark:text-slate-400">Total Validated</div>
                                    <div className="text-xl font-bold font-mono">{analytics.summary.wins + analytics.summary.losses}</div>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4 relative z-10">
                                <div className="bg-emerald-50 dark:bg-emerald-900/20 p-4 rounded-xl border border-emerald-100 dark:border-emerald-800/50">
                                    <div className="text-emerald-700 dark:text-emerald-400 text-xs font-bold uppercase mb-1">True Positives</div>
                                    <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{analytics.summary.wins}</div>
                                    <div className="text-[10px] text-emerald-600/70">WINS</div>
                                </div>
                                <div className="bg-rose-50 dark:bg-rose-900/20 p-4 rounded-xl border border-rose-100 dark:border-rose-800/50">
                                    <div className="text-rose-700 dark:text-rose-400 text-xs font-bold uppercase mb-1">False Positives</div>
                                    <div className="text-2xl font-bold text-rose-600 dark:text-rose-400">{analytics.summary.losses}</div>
                                    <div className="text-[10px] text-rose-600/70">LOSSES</div>
                                </div>
                            </div>
                        </div>

                        {/* 2. AI Agreement (Donut Chart) */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm col-span-1 lg:col-span-2">
                            <h3 className="text-lg font-bold mb-2 flex items-center gap-2">
                                <Brain className="w-5 h-5 text-blue-500" />
                                Logic vs Vision Consensus
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
                                <div className="h-64 w-full">
                                    <Chart
                                        options={agreementOptions}
                                        series={agreementSeries}
                                        type="donut"
                                        height="100%"
                                    />
                                </div>
                                <div className="space-y-4">
                                    <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-800 text-sm">
                                        <div className="font-bold text-slate-700 dark:text-slate-200 mb-1">Why trades are vetoed:</div>
                                        <ul className="space-y-2 text-slate-600 dark:text-slate-400">
                                            <li className="flex items-start gap-2">
                                                <span className="w-2 h-2 mt-1.5 rounded-full bg-amber-500 shrink-0"></span>
                                                <span><strong className="text-amber-500">Vision Veto:</strong> Charts look ugly/choppy despite logic saying yes.</span>
                                            </li>
                                            <li className="flex items-start gap-2">
                                                <span className="w-2 h-2 mt-1.5 rounded-full bg-rose-500 shrink-0"></span>
                                                <span><strong className="text-rose-500">Logic Veto:</strong> Fundamentals/indicators weak despite nice chart.</span>
                                            </li>
                                            <li className="flex items-start gap-2">
                                                <span className="w-2 h-2 mt-1.5 rounded-full bg-emerald-500 shrink-0"></span>
                                                <span><strong className="text-emerald-500">Consensus:</strong> Both specific models agree on direction.</span>
                                            </li>
                                        </ul>
                                    </div>
                                    <div className="grid grid-cols-3 gap-2 text-center text-xs">
                                        <div className="p-2 bg-slate-50 dark:bg-slate-800 rounded">
                                            <div className="font-bold text-slate-900 dark:text-white">{analytics.summary.total_analyzed}</div>
                                            <div className="text-slate-500">Scanned</div>
                                        </div>
                                        <div className="p-2 bg-slate-50 dark:bg-slate-800 rounded">
                                            <div className="font-bold text-slate-900 dark:text-white">{analytics.summary.total_execute}</div>
                                            <div className="text-slate-500">Signals</div>
                                        </div>
                                        <div className="p-2 bg-slate-50 dark:bg-slate-800 rounded">
                                            <div className="font-bold text-slate-900 dark:text-white">{analytics.summary.execute_rate}%</div>
                                            <div className="text-slate-500">Rate</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ROW 2: Confidence & Whales */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                        {/* 3. Confidence Histogram */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                                <Activity className="w-5 h-5 text-amber-500" />
                                Confidence Distribution
                            </h3>
                            <div className="h-64">
                                <Chart
                                    options={confidenceOptions}
                                    series={confidenceSeries}
                                    type="bar"
                                    height="100%"
                                />
                            </div>
                            <p className="text-xs text-center text-slate-500 mt-2">
                                Probability distribution of AI confidence scores for generated signals.
                            </p>
                        </div>

                        {/* 4. Whale Sentiment Gauge */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                                <Users className="w-5 h-5 text-pink-500" />
                                Whale Signal Sentiment
                            </h3>
                            <div className="h-64">
                                <Chart
                                    options={whaleOptions}
                                    series={whaleSeries}
                                    type="bar"
                                    height="100%"
                                />
                            </div>
                            <div className="flex justify-between text-xs text-slate-500 px-4">
                                <span className="text-rose-500 font-bold">BEARISH (Dump/Squeeze)</span>
                                <span className="text-emerald-500 font-bold">BULLISH (Pump/Squeeze)</span>
                            </div>
                        </div>
                    </div>

                    {/* ROW 3: Hourly Activity (Kept from old design but wrapped nicely) */}
                    <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-lg font-bold flex items-center gap-2">
                                <Clock className="w-5 h-5 text-indigo-500" />
                                Market Activity Heatmap (UTC)
                            </h3>
                            <div className="text-xs font-mono text-slate-400">24HR CYCLE</div>
                        </div>

                        <div className="flex items-end gap-1 h-32 pb-2">
                            {Array.from({ length: 24 }).map((_, hour) => {
                                const data = analytics.hourly_pattern.find(d => d.hour === hour);
                                const count = data ? data.execute_count : 0;
                                const maxCount = Math.max(...analytics.hourly_pattern.map(d => d.execute_count), 5);
                                const height = (count / maxCount) * 100;

                                return (
                                    <div key={hour} className="flex-1 flex flex-col items-center group relative h-full justify-end">
                                        <div className="absolute bottom-full mb-2 bg-slate-800 text-white text-xs px-2 py-1 rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-10 whitespace-nowrap pointer-events-none">
                                            {hour}:00 UTC • {count} signals
                                        </div>
                                        <div
                                            className={`w-full rounded-t-sm transition-all duration-500 ${count > 0 ? 'bg-indigo-500/80 hover:bg-indigo-400' : 'bg-slate-100 dark:bg-slate-800'}`}
                                            style={{ height: `${Math.max(height, 5)}%` }}
                                        ></div>
                                        <span className="text-[9px] md:text-[10px] text-slate-400 mt-2 font-mono">{hour}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                </div>
            ) : null}
        </div>
    );
}
