import { Brain, Activity, Cpu } from 'lucide-react';
import { AISignalsPanel } from '@/components/dashboard/AISignalsPanel';
import { SystemHealthPanel, BrainHealthPanel } from '@/components/dashboard/SystemHealth';
import { useUser } from '@/hooks/useUser';

export function AdminPage() {
    const { data: user } = useUser();

    // Only admins can access this page
    if (user?.role !== 'admin' && user?.role !== 'ADMIN') {
        return (
            <div className="text-center py-16">
                <Brain className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">
                    Admin Access Required
                </h2>
                <p className="text-slate-500">
                    This page is only accessible to administrators.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* AI Signals Panel */}
                <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                        <div className="p-2 bg-violet-50 dark:bg-violet-900/20 rounded-lg text-violet-600 dark:text-violet-400">
                            <Cpu className="w-5 h-5" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white">AI Signals</h3>
                            <p className="text-sm text-slate-500">Real-time market analysis</p>
                        </div>
                    </div>
                    <AISignalsPanel />
                </div>

                {/* Side Panel */}
                <div className="space-y-6">
                    {/* System Health */}
                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg text-emerald-600 dark:text-emerald-400">
                                <Activity className="w-5 h-5" />
                            </div>
                            <h3 className="font-bold text-slate-900 dark:text-white">System Health</h3>
                        </div>
                        <SystemHealthPanel />
                    </div>

                    {/* Brain Health */}
                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-amber-600 dark:text-amber-400">
                                <Brain className="w-5 h-5" />
                            </div>
                            <h3 className="font-bold text-slate-900 dark:text-white">ML Brain Health</h3>
                        </div>
                        <BrainHealthPanel />
                    </div>
                </div>
            </div>
        </div>
    );
}
