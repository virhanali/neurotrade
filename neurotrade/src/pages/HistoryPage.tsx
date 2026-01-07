import { useTradeHistory } from '@/hooks/usePositions';
import { cn, formatCurrency, formatPercent, getPnlColor, formatDate, getPnlBgColor } from '@/utils/helpers';
import { Loader2 } from 'lucide-react';

export function HistoryPage() {
    const { data: trades, isLoading } = useTradeHistory(100);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                <div className="p-6 border-b border-slate-200 dark:border-slate-800">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                        Trade History
                    </h3>
                    <p className="text-sm text-slate-500 mt-1">
                        {trades?.length || 0} trades recorded
                    </p>
                </div>

                {!trades || trades.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <p className="text-lg">No trade history yet</p>
                        <p className="text-sm mt-1">Your completed trades will appear here</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-slate-50 dark:bg-slate-800/50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Date</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Symbol</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Side</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Entry</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Exit</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">PnL</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Close Reason</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {trades.map((trade) => (
                                    <tr key={trade.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                                        <td className="px-6 py-4 text-sm text-slate-500">
                                            {formatDate(trade.closedAt || trade.createdAt)}
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className="font-semibold text-slate-900 dark:text-white">{trade.symbol}</span>
                                            <span className="ml-2 text-xs text-slate-500">{trade.leverage}x</span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={cn(
                                                'px-2 py-1 rounded text-xs font-bold',
                                                trade.side === 'LONG'
                                                    ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
                                                    : 'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400'
                                            )}>
                                                {trade.side}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-slate-900 dark:text-white font-mono">
                                            {formatCurrency(trade.entryPrice, 4)}
                                        </td>
                                        <td className="px-6 py-4 text-slate-900 dark:text-white font-mono">
                                            {formatCurrency(trade.currentPrice, 4)}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className={cn(
                                                'inline-flex items-center px-2.5 py-1 rounded-lg font-bold',
                                                getPnlBgColor(trade.realizedPnl),
                                                getPnlColor(trade.realizedPnl)
                                            )}>
                                                {formatCurrency(trade.realizedPnl)}
                                                <span className="ml-1.5 text-xs opacity-75">
                                                    ({formatPercent(trade.realizedPnlPercent)})
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={cn(
                                                'px-2 py-1 rounded text-xs font-medium',
                                                trade.closeReason === 'TP' && 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30',
                                                trade.closeReason === 'SL' && 'bg-rose-100 text-rose-600 dark:bg-rose-900/30',
                                                trade.closeReason === 'MANUAL' && 'bg-slate-100 text-slate-600 dark:bg-slate-800',
                                                trade.closeReason === 'LIQUIDATION' && 'bg-red-100 text-red-600 dark:bg-red-900/30'
                                            )}>
                                                {trade.closeReason}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
