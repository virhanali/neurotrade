import { useAISignals } from '@/hooks/useAdmin';
import { cn, getTimeAgo, formatCurrency } from '@/utils/helpers';
import { TrendingUp, TrendingDown, Minus, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import type { AISignal } from '@/types';

type FilterType = 'ALL' | 'RUNNING' | 'WIN' | 'LOSS';

export function AISignalsPanel() {
    const { data: signals, isLoading, error } = useAISignals();
    const [filter, setFilter] = useState<FilterType>('ALL');

    if (isLoading) {
        return (
            <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg animate-pulse">
                        <div className="flex justify-between mb-2">
                            <div className="h-4 w-20 bg-slate-200 dark:bg-slate-700 rounded" />
                            <div className="h-4 w-12 bg-slate-200 dark:bg-slate-700 rounded" />
                        </div>
                        <div className="h-3 w-full bg-slate-200 dark:bg-slate-700 rounded" />
                    </div>
                ))}
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center p-8 text-rose-500">
                <AlertCircle className="w-5 h-5 mr-2" />
                <span>Failed to load signals</span>
            </div>
        );
    }

    const filteredSignals = signals?.filter(s => {
        if (filter === 'ALL') return true;
        if (filter === 'RUNNING') return !s.result || s.result === 'PENDING' || s.result === 'FLOATING' || s.result === 'RUNNING';
        if (filter === 'WIN') return s.result === 'WIN';
        if (filter === 'LOSS') return s.result === 'LOSS';
        return true;
    }) || [];

    return (
        <div>
            {/* Filter Tabs */}
            <div className="flex gap-1 mb-3">
                {(['ALL', 'RUNNING', 'WIN', 'LOSS'] as FilterType[]).map(f => (
                    <button
                        key={f}
                        onClick={() => setFilter(f)}
                        className={cn(
                            'px-3 py-1 text-xs font-medium rounded-lg transition-colors',
                            filter === f
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                                : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'
                        )}
                    >
                        {f}
                    </button>
                ))}
            </div>

            {/* Signals List */}
            <div className="space-y-2 max-h-[400px] overflow-y-auto custom-scrollbar">
                {filteredSignals.length === 0 ? (
                    <div className="text-center py-8 text-slate-500">
                        <Minus className="w-8 h-8 mx-auto mb-2 opacity-30" />
                        <p className="text-sm">No signals found</p>
                    </div>
                ) : (
                    filteredSignals.map(signal => (
                        <SignalCard key={signal.id} signal={signal} />
                    ))
                )}
            </div>
        </div>
    );
}

function SignalCard({ signal }: { signal: AISignal }) {
    const isLong = signal.signal === 'LONG';
    const isWait = signal.signal === 'WAIT';
    const result = signal.result || 'PENDING';
    const isWin = result === 'WIN';
    const isLoss = result === 'LOSS';
    const isFinished = isWin || isLoss;

    return (
        <div className={cn(
            'p-3 rounded-lg border transition-colors',
            isWait
                ? 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700'
                : isFinished
                    ? (isWin
                        ? 'bg-emerald-50/50 dark:bg-emerald-900/10 border-emerald-200 dark:border-emerald-800'
                        : 'bg-rose-50/50 dark:bg-rose-900/10 border-rose-200 dark:border-rose-800')
                    : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700'
        )}>
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-900 dark:text-white">
                        {signal.symbol}
                    </span>
                    <div className="flex gap-1">
                        <span className={cn(
                            'px-1.5 py-0.5 rounded text-xs font-bold',
                            isWait
                                ? 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400'
                                : isLong
                                    ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
                                    : 'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400'
                        )}>
                            {isWait ? 'WAIT' : isLong ? 'LONG' : 'SHORT'}
                        </span>
                        {isFinished && (
                            <span className={cn(
                                'px-1.5 py-0.5 rounded text-xs font-bold uppercase',
                                isWin
                                    ? 'bg-emerald-500 text-white'
                                    : 'bg-rose-500 text-white'
                            )}>
                                {result}
                            </span>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <span className={cn(
                        'text-xs font-bold',
                        signal.confidence >= 75 ? 'text-emerald-500' :
                            signal.confidence >= 50 ? 'text-amber-500' : 'text-slate-500'
                    )}>
                        {signal.confidence}%
                    </span>
                    {!isWait && (
                        isLong ? (
                            <TrendingUp className="w-4 h-4 text-emerald-500" />
                        ) : (
                            <TrendingDown className="w-4 h-4 text-rose-500" />
                        )
                    )}
                </div>
            </div>

            {/* Reasoning */}
            <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 mb-2">
                {signal.reasoning}
            </p>

            {/* Meta */}
            <div className="flex items-center justify-between text-xs text-slate-500">
                <div className="flex gap-3">
                    <span>ML: {Math.round((signal.mlWinProbability || 0) * 100)}%</span>
                    {signal.pnl !== undefined && signal.pnl !== 0 && (
                        <span className={cn(
                            'font-bold',
                            signal.pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'
                        )}>
                            {/* If PnL > 100 it is likely dollar, if < 1 likely percent? 
                        Backend sends whatever is in metrics.PnL (dollar).
                        But wait, logic in handler: pnlVal = metrics.PnL.
                        Let's format as currency.
                    */}
                            {formatCurrency(signal.pnl)}
                        </span>
                    )}
                </div>
                <span>{getTimeAgo(signal.createdAt)}</span>
            </div>
        </div>
    );
}
