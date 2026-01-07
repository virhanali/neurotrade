import { useState, useEffect } from 'react';
import {
    BarChart,
    Brain,
    CheckCircle,
    Clock,
    TrendingUp,
    Users,
    Zap,
    AlertTriangle,
    RefreshCw,
    Database
} from 'lucide-react';

interface AIAnalytics {
    status: string;
    summary: {
        total_analyzed: number;
        total_execute: number;
        with_outcome: number;
        execute_rate: number;
        ai_agreement_rate: number;
    };
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

        // Auto refresh every 60s
        const interval = setInterval(() => {
            // Silent refresh
            fetch('/api/ml/analytics')
                .then(res => res.json())
                .then(data => setAnalytics(data))
                .catch(console.error);
        }, 60000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="space-y-6 animate-fade-in text-slate-800 dark:text-slate-100">
            <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800">
                <div>
                    <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-500 to-pink-600">
                        AI Brain Center
                    </h1>
                    <p className="text-slate-500 dark:text-slate-400 mt-1 text-sm">Deep Learning Insights & Behavior Analytics</p>
                </div>
                <div className="flex gap-3">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-400">
                        <Clock className="w-3.5 h-3.5" />
                        <span>Last 7 Days</span>
                    </div>
                    <button
                        onClick={fetchAnalytics}
                        className="p-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors text-slate-600 dark:text-slate-400"
                        title="Refresh Data"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </header>

            {loading && !analytics ? (
                <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-purple-500"></div>
                </div>
            ) : error ? (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 rounded-xl text-red-600 dark:text-red-400 flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5" />
                    {error}
                </div>
            ) : analytics ? (
                <div className="space-y-6">
                    {/* Top Stats Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-purple-500/30 transition-all">
                            <div className="flex justify-between items-start mb-4">
                                <div className="p-3 bg-purple-100 dark:bg-purple-900/20 rounded-xl">
                                    <Brain className="w-6 h-6 text-purple-600 dark:text-purple-400" />
                                </div>
                                <span className="text-xs font-bold text-slate-400 dark:text-slate-500 tracking-wider">TOTAL ANALYZED</span>
                            </div>
                            <div className="text-3xl font-bold mb-1">
                                {analytics.summary.total_analyzed.toLocaleString()}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400">
                                {analytics.summary.total_execute} Executed ({analytics.summary.execute_rate}%)
                            </div>
                        </div>

                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-blue-500/30 transition-all">
                            <div className="flex justify-between items-start mb-4">
                                <div className="p-3 bg-blue-100 dark:bg-blue-900/20 rounded-xl">
                                    <CheckCircle className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                                </div>
                                <span className="text-xs font-bold text-slate-400 dark:text-slate-500 tracking-wider">AI AGREEMENT</span>
                            </div>
                            <div className="text-3xl font-bold mb-1">
                                {analytics.summary.ai_agreement_rate}%
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400">
                                Logic vs Vision Consensus
                            </div>
                        </div>

                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-emerald-500/30 transition-all">
                            <div className="flex justify-between items-start mb-4">
                                <div className="p-3 bg-emerald-100 dark:bg-emerald-900/20 rounded-xl">
                                    <TrendingUp className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                                </div>
                                <span className="text-xs font-bold text-slate-400 dark:text-slate-500 tracking-wider">LEARNING DATA</span>
                            </div>
                            <div className="text-3xl font-bold mb-1">
                                {analytics.summary.with_outcome}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400">
                                Samples with Outcomes (Win/Loss)
                            </div>
                        </div>

                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-amber-500/30 transition-all">
                            <div className="flex justify-between items-start mb-4">
                                <div className="p-3 bg-amber-100 dark:bg-amber-900/20 rounded-xl">
                                    <Zap className="w-6 h-6 text-amber-600 dark:text-amber-400" />
                                </div>
                                <span className="text-xs font-bold text-slate-400 dark:text-slate-500 tracking-wider">OPPORTUNITIES</span>
                            </div>
                            <div className="text-3xl font-bold mb-1">
                                {analytics.summary.total_execute}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400">
                                High Confidence Signals
                            </div>
                        </div>
                    </div>

                    {/* Main Content Grid */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                        {/* Confidence Distribution */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800">
                            <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
                                <BarChart className="w-5 h-5 text-purple-500" />
                                Confidence Level
                            </h3>
                            <div className="space-y-4">
                                {analytics.confidence_distribution.map((item, idx) => (
                                    <div key={idx}>
                                        <div className="flex justify-between text-sm mb-1">
                                            <span className="text-slate-600 dark:text-slate-300 font-medium">{item.level}</span>
                                            <span className="text-slate-500 dark:text-slate-400 font-mono">{item.count}</span>
                                        </div>
                                        <div className="h-2.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                            <div
                                                className={`h-full rounded-full ${item.level.includes('HIGH') ? 'bg-emerald-500' :
                                                        item.level.includes('MEDIUM') ? 'bg-amber-500' : 'bg-rose-500'
                                                    }`}
                                                style={{ width: `${(item.count / analytics.summary.total_analyzed) * 100}%` }}
                                            ></div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Hourly Activity Heatmap */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 col-span-1 lg:col-span-2">
                            <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
                                <Clock className="w-5 h-5 text-blue-500" />
                                Actionable Hours (UTC)
                            </h3>
                            <div className="flex items-end gap-1 h-44 pb-2">
                                {Array.from({ length: 24 }).map((_, hour) => {
                                    const data = analytics.hourly_pattern.find(d => d.hour === hour);
                                    const count = data ? data.execute_count : 0;
                                    const maxCount = Math.max(...analytics.hourly_pattern.map(d => d.execute_count), 5); // Avoid division by zero
                                    const height = (count / maxCount) * 100;

                                    return (
                                        <div key={hour} className="flex-1 flex flex-col items-center group relative h-full justify-end">
                                            {/* Tooltip */}
                                            <div className="absolute bottom-full mb-2 bg-slate-800 text-white text-xs px-2 py-1 rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-10 whitespace-nowrap pointer-events-none">
                                                {hour}:00 UTC • {count} signals
                                            </div>

                                            <div
                                                className={`w-full rounded-t-sm transition-all duration-500 ${count > 0 ? 'bg-blue-500/80 hover:bg-blue-400' : 'bg-slate-100 dark:bg-slate-800'}`}
                                                style={{ height: `${Math.max(height, 4)}%` }}
                                            ></div>
                                            <span className="text-[9px] md:text-[10px] text-slate-400 mt-2 font-mono">{hour}</span>
                                        </div>
                                    );
                                })}
                            </div>
                            <p className="text-xs text-center text-slate-500 mt-2">Bars indicate number of executed signals per hour.</p>
                        </div>
                    </div>

                    {/* Whale & Symbols Grid */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Whale Signals */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800">
                            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                                <Users className="w-5 h-5 text-pink-500" />
                                Whale Signal Tracking
                            </h3>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead>
                                        <tr className="text-xs font-bold text-slate-400 border-b border-slate-200 dark:border-slate-800">
                                            <th className="pb-3 px-2">SIGNAL TYPE</th>
                                            <th className="pb-3 px-2 text-right">COUNT</th>
                                            <th className="pb-3 px-2 text-right">AVG CONF.</th>
                                        </tr>
                                    </thead>
                                    <tbody className="text-sm">
                                        {analytics.whale_signals.map((item, idx) => (
                                            <tr key={idx} className="border-b border-slate-100 dark:border-slate-800 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                                                <td className="py-3 px-2 font-medium text-slate-700 dark:text-slate-300">{item.signal}</td>
                                                <td className="py-3 px-2 text-right font-mono text-slate-500 dark:text-slate-400">{item.count}</td>
                                                <td className="py-3 px-2 text-right">
                                                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${item.avg_confidence > 70
                                                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                                                            : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                                                        }`}>
                                                        {item.avg_confidence}%
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* Top Symbols */}
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800">
                            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                                <TrendingUp className="w-5 h-5 text-amber-500" />
                                Most Analyzed Assets
                            </h3>
                            <div className="space-y-3">
                                {analytics.top_symbols.slice(0, 5).map((item, idx) => (
                                    <div key={idx} className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                                        <div className="flex items-center gap-3">
                                            <div className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 text-xs font-mono text-slate-600 dark:text-slate-400">
                                                {idx + 1}
                                            </div>
                                            <span className="font-bold text-slate-800 dark:text-slate-200">{item.symbol}</span>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <div className="text-right">
                                                <div className="text-[10px] text-slate-400 uppercase">Score</div>
                                                <div className="text-sm font-mono font-medium text-blue-600 dark:text-blue-400">{item.avg_score}</div>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-[10px] text-slate-400 uppercase">Conf</div>
                                                <div className={`text-sm font-mono font-bold ${item.avg_confidence > 70 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500'}`}>
                                                    {item.avg_confidence}%
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Backfill Info Card */}
                    <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-6 rounded-xl shadow-lg flex items-center justify-between text-white">
                        <div>
                            <h3 className="text-lg font-bold flex items-center gap-2">
                                <Database className="w-5 h-5 text-indigo-200" />
                                Learning Database
                            </h3>
                            <p className="text-indigo-100 text-sm mt-1 max-w-lg">
                                AI is continuously learning from market movements. Outcomes are simulated via historical backfill every 6 hours to improve future predictions.
                            </p>
                        </div>
                        <div className="text-right pl-4 border-l border-indigo-400/30">
                            <div className="text-3xl font-bold">{analytics.summary.with_outcome}</div>
                            <div className="text-xs text-indigo-200 uppercase tracking-wider">Samples</div>
                        </div>
                    </div>

                </div>
            ) : null}
        </div>
    );
}
