import { useSystemHealth, useBrainHealth } from '@/hooks/useAdmin';
import { cn } from '@/utils/helpers';
import { Brain, Database, Cloud, Loader2, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export function SystemHealthPanel() {
    const { data: health, isLoading, error } = useSystemHealth();

    if (isLoading) {
        return (
            <div className="flex items-center gap-2 text-slate-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Checking...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center gap-2 text-rose-500">
                <XCircle className="w-4 h-4" />
                <span className="text-sm">Error</span>
            </div>
        );
    }

    const services = [
        { name: 'API', status: health?.api_status || 'online', icon: Cloud },
        { name: 'Database', status: health?.db_status || 'online', icon: Database },
        { name: 'AI Engine', status: health?.ai_status || 'online', icon: Brain },
    ];

    return (
        <div className="space-y-2">
            {services.map(service => (
                <div key={service.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                        <service.icon className="w-4 h-4" />
                        <span>{service.name}</span>
                    </div>
                    <StatusBadge status={service.status} />
                </div>
            ))}
        </div>
    );
}

function StatusBadge({ status }: { status: string }) {
    const isOnline = status === 'online' || status === 'healthy' || status === 'ok';
    const isWarning = status === 'degraded' || status === 'slow';

    return (
        <div className={cn(
            'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
            isOnline && 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
            isWarning && 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
            !isOnline && !isWarning && 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400'
        )}>
            {isOnline ? (
                <CheckCircle className="w-3 h-3" />
            ) : isWarning ? (
                <AlertTriangle className="w-3 h-3" />
            ) : (
                <XCircle className="w-3 h-3" />
            )}
            <span className="capitalize">{status}</span>
        </div>
    );
}

export function BrainHealthPanel() {
    const { data, isLoading, error } = useBrainHealth();

    if (isLoading) {
        return (
            <div className="animate-pulse space-y-4">
                <div className="h-4 w-full bg-slate-200 dark:bg-slate-700 rounded" />
                <div className="h-4 w-full bg-slate-200 dark:bg-slate-700 rounded" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="text-center py-4 text-slate-500">
                <Brain className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">Could not load brain health</p>
            </div>
        );
    }

    const samples = data?.data?.samples || 0;
    const minSamples = data?.data?.required_samples || 50;
    const progress = Math.min((samples / minSamples) * 100, 100);
    const isActive = samples >= minSamples;

    return (
        <div>
            <div className="flex items-center justify-between mb-2 text-sm">
                <span className="text-slate-500 dark:text-slate-400">
                    Progress: <span className="font-bold text-slate-900 dark:text-white">{samples}</span> / {minSamples} Trades
                </span>
                <span className={cn(
                    'px-2 py-0.5 rounded-full text-xs font-bold',
                    isActive
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                )}>
                    {isActive ? 'Active' : 'Learning'}
                </span>
            </div>

            <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-4 overflow-hidden">
                <div
                    className="bg-emerald-500 h-4 rounded-full transition-all duration-1000 relative overflow-hidden"
                    style={{ width: `${progress}%` }}
                >
                    <div className="absolute inset-0 bg-white/20 animate-pulse" />
                </div>
            </div>

            <p className="text-xs text-slate-400 mt-2">
                ML model requires {minSamples} closed trades to activate self-learning capabilities.
            </p>

            {isActive && data?.data?.win_rate && (
                <div className="mt-4 grid grid-cols-2 gap-4">
                    <div className="text-center p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
                        <p className="text-2xl font-bold text-emerald-500">
                            {(data.data.win_rate * 100).toFixed(1)}%
                        </p>
                        <p className="text-xs text-slate-500">Win Rate</p>
                    </div>
                    <div className="text-center p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">
                            {samples}
                        </p>
                        <p className="text-xs text-slate-500">Total Trades</p>
                    </div>
                </div>
            )}
        </div>
    );
}
