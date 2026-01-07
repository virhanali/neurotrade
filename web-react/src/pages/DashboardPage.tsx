import { useState } from 'react';
import { TrendingUp, TrendingDown, Target, Percent, DollarSign, BarChart3 } from 'lucide-react';
import { useUser } from '@/hooks/useUser';
import { usePositions, useDashboardStats } from '@/hooks/usePositions';
import { cn, formatCurrency, formatPercent, getPnlColor } from '@/utils/helpers';
import { PerformanceChart } from '@/components/dashboard/PerformanceChart';
import { PendingApprovals, PanicButton } from '@/components/dashboard/PendingApprovals';
import { AISignalsPanel } from '@/components/dashboard/AISignalsPanel';
import { SystemHealthPanel } from '@/components/dashboard/SystemHealth';
import type { Position } from '@/types';

export function DashboardPage() {
    const { data: user, isLoading: userLoading } = useUser();
    const { data: positions } = usePositions();
    const { data: stats, isLoading: statsLoading } = useDashboardStats();
    const [chartPeriod, setChartPeriod] = useState<'24h' | '7d'>('24h');

    const openPositions = positions?.filter((p: Position) => p.status === 'OPEN') || [];
    const pendingPositions = positions?.filter((p: Position) =>
        p.status === 'PENDING_APPROVAL' || p.status === 'PENDING'
    ) || [];

    const isAdmin = user?.role === 'admin' || user?.role === 'ADMIN';

    if (userLoading || statsLoading) {
        return (
            <div className="animate-pulse space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="h-32 bg-slate-200 dark:bg-slate-800 rounded-xl" />
                    ))}
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* Total Balance */}
                <StatCard
                    title="Total Equity"
                    value={formatCurrency(user?.mode === 'REAL' ? (user.realBalanceCache || 0) : (user?.paperBalance || 0))}
                    subtitle={user?.mode || 'PAPER'}
                    subtitleColor={user?.mode === 'REAL' ? 'rose' : 'slate'}
                    icon={DollarSign}
                    iconBg="emerald"
                />

                {/* Today's PnL */}
                <StatCard
                    title="Today's PnL"
                    value={formatCurrency(stats?.todayPnl || 0)}
                    subtitle={formatPercent(stats?.todayPnlPercent || 0)}
                    subtitleColor={(stats?.todayPnl || 0) >= 0 ? 'emerald' : 'rose'}
                    icon={(stats?.todayPnl || 0) >= 0 ? TrendingUp : TrendingDown}
                    iconBg={(stats?.todayPnl || 0) >= 0 ? 'emerald' : 'rose'}
                />

                {/* Win Rate */}
                <StatCard
                    title="Win Rate"
                    value={`${((stats?.winRate || 0) * 100).toFixed(1)}%`}
                    subtitle={`${stats?.totalWins || 0}W / ${stats?.totalLosses || 0}L`}
                    subtitleColor="amber"
                    icon={Percent}
                    iconBg="amber"
                />

                {/* Total Trades */}
                <StatCard
                    title="Total Trades"
                    value={String(stats?.totalTrades || 0)}
                    subtitle={`Best: ${formatCurrency(stats?.bestTrade || 0)}`}
                    subtitleColor="emerald"
                    icon={Target}
                    iconBg="indigo"
                />
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column - Chart & Positions */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Performance Chart */}
                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg text-indigo-600 dark:text-indigo-400">
                                    <BarChart3 className="w-5 h-5" />
                                </div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                                    Performance
                                </h3>
                            </div>
                            <div className="flex gap-1">
                                <button
                                    onClick={() => setChartPeriod('24h')}
                                    className={cn(
                                        'px-3 py-1 text-xs font-medium rounded-lg transition-colors',
                                        chartPeriod === '24h'
                                            ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400'
                                            : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'
                                    )}
                                >
                                    24H
                                </button>
                                <button
                                    onClick={() => setChartPeriod('7d')}
                                    className={cn(
                                        'px-3 py-1 text-xs font-medium rounded-lg transition-colors',
                                        chartPeriod === '7d'
                                            ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400'
                                            : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'
                                    )}
                                >
                                    7D
                                </button>
                            </div>
                        </div>
                        <PerformanceChart period={chartPeriod} />
                    </div>

                    {/* Open Positions Preview */}
                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                                Open Positions
                            </h3>
                            <span className="text-sm text-slate-500">
                                {openPositions.length} active
                            </span>
                        </div>

                        {openPositions.length === 0 ? (
                            <div className="text-center py-8 text-slate-500">
                                No open positions. AI is scanning for opportunities...
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {openPositions.slice(0, 5).map((position: Position) => (
                                    <div
                                        key={position.id}
                                        className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg"
                                    >
                                        <div className="flex items-center gap-4">
                                            <div className={cn(
                                                'px-2 py-1 rounded text-xs font-bold',
                                                position.side === 'LONG'
                                                    ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
                                                    : 'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400'
                                            )}>
                                                {position.side}
                                            </div>
                                            <div>
                                                <p className="font-semibold text-slate-900 dark:text-white">
                                                    {position.symbol}
                                                </p>
                                                <p className="text-sm text-slate-500">
                                                    {position.leverage}x • {formatCurrency(position.entryPrice, 4)}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <p className={cn('font-bold', getPnlColor(position.unrealizedPnl))}>
                                                {formatCurrency(position.unrealizedPnl)}
                                            </p>
                                            <p className={cn('text-sm', getPnlColor(position.unrealizedPnlPercent))}>
                                                {formatPercent(position.unrealizedPnlPercent)}
                                            </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* Right Column - Admin/Action Panel */}
                <div className="space-y-6">
                    {/* Pending Approvals */}
                    {pendingPositions.length > 0 && (
                        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">
                                Pending Approvals ({pendingPositions.length})
                            </h3>
                            <PendingApprovals />
                        </div>
                    )}

                    {/* AI Signals (Admin only) */}
                    {isAdmin && (
                        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">
                                AI Signals
                            </h3>
                            <AISignalsPanel />
                        </div>
                    )}

                    {/* System Health (Admin only) */}
                    {isAdmin && (
                        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                            <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
                                System Health
                            </h3>
                            <SystemHealthPanel />
                        </div>
                    )}

                    {/* Panic Button */}
                    {openPositions.length > 0 && (
                        <PanicButton />
                    )}
                </div>
            </div>
        </div>
    );
}

interface StatCardProps {
    title: string;
    value: string;
    subtitle: string;
    subtitleColor: 'emerald' | 'rose' | 'amber' | 'slate' | 'indigo';
    icon: React.ElementType;
    iconBg: 'emerald' | 'rose' | 'amber' | 'indigo';
}

function StatCard({ title, value, subtitle, subtitleColor, icon: Icon, iconBg }: StatCardProps) {
    const iconBgColors = {
        emerald: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400',
        rose: 'bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400',
        amber: 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400',
        indigo: 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400',
    };

    const subtitleColors = {
        emerald: 'text-emerald-600 dark:text-emerald-400',
        rose: 'text-rose-600 dark:text-rose-400',
        amber: 'text-amber-600 dark:text-amber-400',
        slate: 'text-slate-500 dark:text-slate-400',
        indigo: 'text-indigo-600 dark:text-indigo-400',
    };

    return (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 hover:border-emerald-500/30 transition-colors">
            <div className="flex justify-between items-start">
                <div>
                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
                    <h3 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{value}</h3>
                    <p className={cn('text-sm mt-1 font-medium', subtitleColors[subtitleColor])}>
                        {subtitle}
                    </p>
                </div>
                <div className={cn('p-3 rounded-xl', iconBgColors[iconBg])}>
                    <Icon className="w-6 h-6" />
                </div>
            </div>
        </div>
    );
}
