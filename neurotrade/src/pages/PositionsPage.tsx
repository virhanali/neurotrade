import { usePositions } from '@/hooks/usePositions';
import { cn, formatCurrency, formatPercent, getPnlColor } from '@/utils/helpers';
import { Loader2, X } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useState } from 'react';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';

export function PositionsPage() {
    const { data: positions, isLoading } = usePositions();
    const openPositions = positions?.filter(p => p.status === 'OPEN') || [];

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
                        Live Positions
                    </h3>
                    <p className="text-sm text-slate-500 mt-1">
                        {openPositions.length} active position{openPositions.length !== 1 ? 's' : ''}
                    </p>
                </div>

                {openPositions.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <p className="text-lg">No open positions</p>
                        <p className="text-sm mt-1">AI is scanning for high-probability setups...</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-slate-50 dark:bg-slate-800/50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Symbol</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Side</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Entry</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Current</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Size</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">PnL</th>
                                    <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">TP / SL</th>
                                    <th className="px-6 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {openPositions.map((position) => (
                                    <PositionRow key={position.id} position={position} />
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

function PositionRow({ position }: { position: any }) {
    const queryClient = useQueryClient();
    const [closing, setClosing] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);

    const closeMutation = useMutation({
        mutationFn: () => api.closePosition(position.id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['positions'] });
            queryClient.invalidateQueries({ queryKey: ['user'] });
        },
    });

    const handleClose = () => {
        setShowConfirm(true);
    };

    const confirmClose = () => {
        setClosing(true);
        closeMutation.mutate();
    };

    return (
        <>
            <tr className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                <td className="px-6 py-4">
                    <span className="font-semibold text-slate-900 dark:text-white">{position.symbol}</span>
                    <span className="ml-2 text-xs text-slate-500">{position.leverage}x</span>
                </td>
                <td className="px-6 py-4">
                    <span className={cn(
                        'px-2 py-1 rounded text-xs font-bold',
                        position.side === 'LONG'
                            ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
                            : 'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400'
                    )}>
                        {position.side}
                    </span>
                </td>
                <td className="px-6 py-4 text-slate-900 dark:text-white font-mono">
                    {formatCurrency(position.entryPrice, 4)}
                </td>
                <td className="px-6 py-4 text-slate-900 dark:text-white font-mono">
                    {formatCurrency(position.currentPrice, 4)}
                </td>
                <td className="px-6 py-4 text-slate-500">
                    {position.size?.toFixed(4)} qty
                </td>
                <td className="px-6 py-4">
                    <div className={cn('font-bold', getPnlColor(position.unrealizedPnl))}>
                        {formatCurrency(position.unrealizedPnl)}
                    </div>
                    <div className={cn('text-sm', getPnlColor(position.unrealizedPnlPercent))}>
                        {formatPercent(position.unrealizedPnlPercent)}
                    </div>
                </td>
                <td className="px-6 py-4 text-sm">
                    <div className="text-emerald-500">TP: {position.tpPrice ? formatCurrency(position.tpPrice, 4) : '-'}</div>
                    <div className="text-rose-500">SL: {position.slPrice ? formatCurrency(position.slPrice, 4) : '-'}</div>
                </td>
                <td className="px-6 py-4 text-right">
                    <button
                        onClick={handleClose}
                        disabled={closing}
                        className="px-3 py-1.5 bg-rose-50 hover:bg-rose-100 dark:bg-rose-900/20 dark:hover:bg-rose-900/40 text-rose-600 dark:text-rose-400 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    >
                        {closing ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
                    </button>
                </td>
            </tr>
            <ConfirmDialog
                isOpen={showConfirm}
                title="Close Position"
                message={`Are you sure you want to close your ${position.side} position on ${position.symbol}?`}
                confirmText="Close Position"
                variant="danger"
                isLoading={closing}
                onConfirm={confirmClose}
                onCancel={() => setShowConfirm(false)}
            />
        </>
    );
}
