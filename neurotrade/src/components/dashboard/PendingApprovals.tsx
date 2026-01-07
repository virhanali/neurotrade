import { useMutation, useQueryClient } from '@tanstack/react-query';
import { usePositions } from '@/hooks/usePositions';
import { cn, formatCurrency, formatDate } from '@/utils/helpers';
import { Loader2, X, Check, AlertTriangle } from 'lucide-react';
import { useState } from 'react';

export function PendingApprovals() {
    const { data: positions } = usePositions();
    const pendingPositions = positions?.filter(p => p.status === 'PENDING_APPROVAL' || p.status === 'PENDING') || [];

    if (pendingPositions.length === 0) {
        return (
            <div className="text-center py-8 text-slate-500">
                <Check className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No pending approvals</p>
                <p className="text-xs mt-1">All signals are processed</p>
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {pendingPositions.map((position) => (
                <PendingCard key={position.id} position={position} />
            ))}
        </div>
    );
}

function PendingCard({ position }: { position: any }) {
    const queryClient = useQueryClient();
    const [loading, setLoading] = useState<'approve' | 'decline' | null>(null);

    const approveMutation = useMutation({
        mutationFn: () => fetch(`/api/user/positions/${position.id}/approve`, { method: 'POST' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['positions'] });
            queryClient.invalidateQueries({ queryKey: ['user'] });
        },
    });

    const declineMutation = useMutation({
        mutationFn: () => fetch(`/api/user/positions/${position.id}/decline`, { method: 'POST' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['positions'] });
        },
    });

    const handleApprove = async () => {
        setLoading('approve');
        await approveMutation.mutateAsync();
        setLoading(null);
    };

    const handleDecline = async () => {
        setLoading('decline');
        await declineMutation.mutateAsync();
        setLoading(null);
    };

    const isLong = position.side === 'LONG';

    return (
        <div className={cn(
            'p-4 rounded-xl border-2 border-dashed',
            isLong
                ? 'border-emerald-300 bg-emerald-50/50 dark:bg-emerald-900/10 dark:border-emerald-800'
                : 'border-rose-300 bg-rose-50/50 dark:bg-rose-900/10 dark:border-rose-800'
        )}>
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-900 dark:text-white">{position.symbol}</span>
                    <span className={cn(
                        'px-2 py-0.5 rounded text-xs font-bold',
                        isLong
                            ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
                            : 'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400'
                    )}>
                        {position.side}
                    </span>
                </div>
                <span className="text-xs text-slate-500">
                    {formatDate(position.createdAt)}
                </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-sm mb-3">
                <div>
                    <p className="text-xs text-slate-500">Entry</p>
                    <p className="font-mono text-slate-900 dark:text-white">
                        {formatCurrency(position.entryPrice, 4)}
                    </p>
                </div>
                <div>
                    <p className="text-xs text-slate-500">SL</p>
                    <p className="font-mono text-rose-500">
                        {formatCurrency(position.stopLoss, 4)}
                    </p>
                </div>
                <div>
                    <p className="text-xs text-slate-500">TP</p>
                    <p className="font-mono text-emerald-500">
                        {formatCurrency(position.takeProfit, 4)}
                    </p>
                </div>
            </div>

            <div className="flex gap-2">
                <button
                    onClick={handleApprove}
                    disabled={loading !== null}
                    className="flex-1 py-2 px-4 bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                    {loading === 'approve' ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <>
                            <Check className="w-4 h-4" />
                            Approve
                        </>
                    )}
                </button>
                <button
                    onClick={handleDecline}
                    disabled={loading !== null}
                    className="flex-1 py-2 px-4 bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-medium rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                    {loading === 'decline' ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <>
                            <X className="w-4 h-4" />
                            Decline
                        </>
                    )}
                </button>
            </div>
        </div>
    );
}

export function PanicButton() {
    const queryClient = useQueryClient();
    const [loading, setLoading] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);

    const panicMutation = useMutation({
        mutationFn: () => fetch('/api/user/panic-button', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['positions'] });
            queryClient.invalidateQueries({ queryKey: ['user'] });
            setShowConfirm(false);
        },
    });

    const handlePanic = async () => {
        setLoading(true);
        await panicMutation.mutateAsync();
        setLoading(false);
    };

    if (!showConfirm) {
        return (
            <button
                onClick={() => setShowConfirm(true)}
                className="w-full py-3 px-4 bg-rose-50 hover:bg-rose-100 dark:bg-rose-900/20 dark:hover:bg-rose-900/40 text-rose-600 dark:text-rose-400 font-bold rounded-xl border-2 border-dashed border-rose-300 dark:border-rose-800 transition-all flex items-center justify-center gap-2"
            >
                <AlertTriangle className="w-5 h-5" />
                PANIC: Close All Positions
            </button>
        );
    }

    return (
        <div className="p-4 bg-rose-50 dark:bg-rose-900/20 rounded-xl border-2 border-rose-300 dark:border-rose-800">
            <p className="text-rose-600 dark:text-rose-400 font-medium mb-3 text-center">
                ⚠️ This will close ALL open positions immediately!
            </p>
            <div className="flex gap-2">
                <button
                    onClick={() => setShowConfirm(false)}
                    disabled={loading}
                    className="flex-1 py-2 px-4 bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-medium rounded-lg transition-colors"
                >
                    Cancel
                </button>
                <button
                    onClick={handlePanic}
                    disabled={loading}
                    className="flex-1 py-2 px-4 bg-rose-500 hover:bg-rose-600 text-white font-bold rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                    {loading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        'CONFIRM'
                    )}
                </button>
            </div>
        </div>
    );
}
