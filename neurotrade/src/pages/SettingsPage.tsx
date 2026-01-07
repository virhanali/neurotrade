import { useState, useEffect } from 'react';
import { useUser, useUpdateSettings } from '@/hooks/useUser';
import { Loader2, AlertTriangle, CheckCircle, Gamepad2, Shield, Zap, Eye, EyeOff, Pencil, X } from 'lucide-react';
import { cn, formatCurrency } from '@/utils/helpers';

export function SettingsPage() {
    const { data: user, isLoading } = useUser();
    const updateSettings = useUpdateSettings();

    // Form state
    const [mode, setMode] = useState<'PAPER' | 'REAL'>('PAPER');
    const [fixedOrderSize, setFixedOrderSize] = useState('10.00');
    const [leverage, setLeverage] = useState('20');
    const [autoTradeEnabled, setAutoTradeEnabled] = useState(false);

    // API Key State
    const [apiKey, setApiKey] = useState('');
    const [apiSecret, setApiSecret] = useState('');
    const [showApiKey, setShowApiKey] = useState(false);
    const [showApiSecret, setShowApiSecret] = useState(false);
    const [isEditingKey, setIsEditingKey] = useState(false);
    const [isEditingSecret, setIsEditingSecret] = useState(false);

    // Toast state
    const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

    // Sync form state with user data
    useEffect(() => {
        if (user) {
            setMode(user.mode);
            setFixedOrderSize(user.fixedOrderSize.toFixed(2));
            setLeverage(user.leverage.toString());
            setAutoTradeEnabled(user.autoTradeEnabled);
            setApiKey(user.binanceApiKey || '');
            // We don't sync secret back from backend for security, it is write-only typically or masked
            // If we want to show it's set, we handle that in the UI rendering logic
        }
    }, [user]);

    // Clear toast after 3 seconds
    useEffect(() => {
        if (toast) {
            const timer = setTimeout(() => setToast(null), 3000);
            return () => clearTimeout(timer);
        }
    }, [toast]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        try {
            await updateSettings.mutateAsync({
                mode,
                fixedOrderSize: parseFloat(fixedOrderSize),
                leverage: parseInt(leverage),
                autoTradeEnabled,
                binanceApiKey: apiKey,
                binanceApiSecret: apiSecret,
            });
            setToast({ message: 'Settings saved successfully!', type: 'success' });
            // Reset edit modes
            setIsEditingKey(false);
            setIsEditingSecret(false);
        } catch (error: any) {
            setToast({
                message: error.response?.data?.error || 'Failed to save settings',
                type: 'error'
            });
        }
    };

    // Validation
    const orderSize = parseFloat(fixedOrderSize) || 0;
    const lev = parseInt(leverage) || 1;
    const notional = orderSize * lev;
    const isValidNotional = notional >= 5;
    const isFormValid = orderSize >= 1 && (mode === 'PAPER' || isValidNotional);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
            </div>
        );
    }

    return (
        <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
            {/* Toast */}
            {toast && (
                <div className={cn(
                    'fixed top-4 right-4 z-50 flex items-start gap-3 px-5 py-4 rounded-xl shadow-2xl animate-slide-up max-w-md',
                    toast.type === 'success'
                        ? 'bg-emerald-100 text-emerald-800 border-2 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-300 dark:border-emerald-700'
                        : 'bg-rose-100 text-rose-800 border-2 border-rose-300 dark:bg-rose-900/40 dark:text-rose-300 dark:border-rose-700'
                )}>
                    {toast.type === 'success' ? (
                        <CheckCircle className="w-6 h-6 shrink-0 mt-0.5" />
                    ) : (
                        <AlertTriangle className="w-6 h-6 shrink-0 mt-0.5" />
                    )}
                    <span className="font-semibold text-sm leading-relaxed">{toast.message}</span>
                    <button
                        onClick={() => setToast(null)}
                        className="ml-auto shrink-0 p-1.5 hover:bg-black/10 dark:hover:bg-white/10 rounded-lg transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* Trading Mode */}
                <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                        <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg text-indigo-600 dark:text-indigo-400">
                            <Gamepad2 className="w-5 h-5" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Trading Mode</h3>
                            <p className="text-sm text-slate-500">Select your operation environment</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {/* Paper Mode */}
                        <label className={cn(
                            'relative flex items-start p-4 border-2 rounded-xl cursor-pointer transition-all duration-200',
                            mode === 'PAPER'
                                ? 'border-emerald-500 bg-emerald-50/30 dark:bg-emerald-900/10'
                                : 'border-slate-200 dark:border-slate-700 hover:border-emerald-200'
                        )}>
                            <input
                                type="radio"
                                name="mode"
                                value="PAPER"
                                checked={mode === 'PAPER'}
                                onChange={() => setMode('PAPER')}
                                className="sr-only"
                            />
                            <div className={cn(
                                'mt-1 mr-4 flex-shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors',
                                mode === 'PAPER'
                                    ? 'border-emerald-500 bg-emerald-500'
                                    : 'border-slate-300 dark:border-slate-600'
                            )}>
                                {mode === 'PAPER' && <div className="w-2.5 h-2.5 rounded-full bg-white" />}
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="font-bold text-slate-900 dark:text-white text-lg">Simulation Mode</span>
                                    <span className="px-2 py-0.5 rounded text-xs font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400">
                                        RISK FREE
                                    </span>
                                </div>
                                <p className="text-sm text-slate-500 leading-relaxed">
                                    Practice your strategies with virtual funds. Perfect for testing without risking real capital.
                                </p>
                            </div>
                        </label>

                        {/* Real Mode */}
                        <label className={cn(
                            'relative flex items-start p-4 border-2 rounded-xl cursor-pointer transition-all duration-200',
                            mode === 'REAL'
                                ? 'border-rose-500 bg-rose-50/30 dark:bg-rose-900/10'
                                : 'border-slate-200 dark:border-slate-700 hover:border-rose-200'
                        )}>
                            <input
                                type="radio"
                                name="mode"
                                value="REAL"
                                checked={mode === 'REAL'}
                                onChange={() => setMode('REAL')}
                                className="sr-only"
                            />
                            <div className={cn(
                                'mt-1 mr-4 flex-shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors',
                                mode === 'REAL'
                                    ? 'border-rose-500 bg-rose-500'
                                    : 'border-slate-300 dark:border-slate-600'
                            )}>
                                {mode === 'REAL' && <div className="w-2.5 h-2.5 rounded-full bg-white" />}
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="font-bold text-slate-900 dark:text-white text-lg">Live Trading</span>
                                    <span className="px-2 py-0.5 rounded text-xs font-bold bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400">
                                        REAL MONEY
                                    </span>
                                </div>
                                <p className="text-sm text-slate-500 leading-relaxed">
                                    Execute real orders on Binance Futures. High risk, high reward implementation.
                                </p>
                            </div>
                        </label>
                    </div>
                </div>

                {/* Risk Configuration */}
                <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                        <div className="p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-amber-600 dark:text-amber-400">
                            <Shield className="w-5 h-5" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Risk Configuration</h3>
                            <p className="text-sm text-slate-500">Manage your sizing and leverage</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                        {/* Fixed Margin */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                Fixed Margin (USDT) <span className="text-rose-500">*</span>
                            </label>
                            <div className="relative">
                                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                    <span className="text-slate-500">$</span>
                                </div>
                                <input
                                    type="number"
                                    step="0.01"
                                    min="1"
                                    max="1000"
                                    value={fixedOrderSize}
                                    onChange={(e) => setFixedOrderSize(e.target.value)}
                                    className="w-full pl-7 pr-4 py-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-slate-900 dark:text-white"
                                    required
                                />
                            </div>
                            <p className="mt-1 text-xs text-slate-500">
                                Your initial capital per trade. <span className="text-rose-500 font-medium">Minimum: $1.00</span>
                                {mode === 'REAL' && (
                                    <span className={cn(
                                        'ml-2',
                                        isValidNotional ? 'text-emerald-500' : 'text-rose-500'
                                    )}>
                                        | Notional: {formatCurrency(notional)} {isValidNotional ? '✓' : '(Min $5)'}
                                    </span>
                                )}
                            </p>
                        </div>

                        {/* Leverage */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                Leverage
                            </label>
                            <div className="relative">
                                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                    <span className="text-slate-500 font-bold text-sm">x</span>
                                </div>
                                <select
                                    value={leverage}
                                    onChange={(e) => setLeverage(e.target.value)}
                                    className="w-full pl-8 pr-10 py-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-slate-900 dark:text-white appearance-none cursor-pointer"
                                    required
                                >
                                    <option value="1">1x (Spot / No Leverage)</option>
                                    <option value="5">5x (Low Risk)</option>
                                    <option value="10">10x (Moderate)</option>
                                    <option value="20">20x (Standard)</option>
                                    <option value="50">50x (High Risk)</option>
                                    <option value="75">75x (Degen Mode)</option>
                                </select>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">Multiplier for your position size.</p>
                        </div>
                    </div>
                </div>

                {/* Auto Trading */}
                <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                        <div className="p-2 bg-violet-50 dark:bg-violet-900/20 rounded-lg text-violet-600 dark:text-violet-400">
                            <Zap className="w-5 h-5" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Automation</h3>
                            <p className="text-sm text-slate-500">Control AI trading behavior</p>
                        </div>
                    </div>

                    <label className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl cursor-pointer group">
                        <div>
                            <p className="font-medium text-slate-900 dark:text-white">Auto-Trade</p>
                            <p className="text-sm text-slate-500">
                                Allow AI to automatically execute high-confidence trades
                            </p>
                        </div>
                        <div className="relative">
                            <input
                                type="checkbox"
                                checked={autoTradeEnabled}
                                onChange={(e) => setAutoTradeEnabled(e.target.checked)}
                                className="sr-only peer"
                            />
                            <div className={cn(
                                'w-14 h-8 rounded-full transition-colors',
                                autoTradeEnabled
                                    ? 'bg-emerald-500'
                                    : 'bg-slate-300 dark:bg-slate-600'
                            )}>
                                <div className={cn(
                                    'absolute top-1 left-1 w-6 h-6 bg-white rounded-full shadow transition-transform',
                                    autoTradeEnabled && 'translate-x-6'
                                )} />
                            </div>
                        </div>
                    </label>
                </div>

                {/* Exchange Connection */}
                <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                        <div className="p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-yellow-600 dark:text-yellow-400">
                            <Shield className="w-5 h-5" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Exchange Keys</h3>
                            <p className="text-sm text-slate-500">Connect your Binance Futures account</p>
                        </div>
                    </div>

                    <div className="space-y-4">
                        {/* API Key Field */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                API Key
                            </label>
                            <div className="relative">
                                <input
                                    type={showApiKey ? "text" : "password"}
                                    value={apiKey}
                                    onChange={(e) => setApiKey(e.target.value)}
                                    // If user has key and NOT editing, show mask. Else show placeholder.
                                    placeholder={user?.binanceApiKey && !isEditingKey ? "••••••••••••••••••••••••" : "Enter your Binance API Key"}
                                    // Disable if user has key and NOT editing
                                    disabled={!!user?.binanceApiKey && !isEditingKey}
                                    className={cn(
                                        "w-full px-4 py-2.5 pr-20 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-slate-900 dark:text-white",
                                        !!user?.binanceApiKey && !isEditingKey && "opacity-60 cursor-not-allowed"
                                    )}
                                />
                                <div className="absolute right-2 top-1.5 flex items-center gap-1">
                                    {/* Edit / Cancel Key Button */}
                                    {user?.binanceApiKey && (
                                        <button
                                            type="button"
                                            onClick={() => {
                                                if (isEditingKey) {
                                                    // Cancel Edit: Revert to masked (or stored value logic if available, here rely on refresh or just show masked)
                                                    setApiKey(user.binanceApiKey || '');
                                                    setIsEditingKey(false);
                                                } else {
                                                    // Start Edit: Clear the field for security so they type new one
                                                    setApiKey('');
                                                    setIsEditingKey(true);
                                                }
                                            }}
                                            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors rounded-md hover:bg-slate-200 dark:hover:bg-slate-700"
                                            title={isEditingKey ? "Cancel Edit" : "Edit API Key"}
                                        >
                                            {isEditingKey ? <X className="w-4 h-4" /> : <Pencil className="w-4 h-4" />}
                                        </button>
                                    )}

                                    {/* Show/Hide Toggle - only show when there's actual value */}
                                    {apiKey && (
                                        <button
                                            type="button"
                                            onClick={() => setShowApiKey(!showApiKey)}
                                            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors rounded-md hover:bg-slate-200 dark:hover:bg-slate-700"
                                            title={showApiKey ? "Hide Key" : "Show Key"}
                                        >
                                            {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* API Secret Field */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                API Secret
                            </label>
                            <div className="relative">
                                <input
                                    type={showApiSecret ? "text" : "password"}
                                    value={apiSecret}
                                    onChange={(e) => setApiSecret(e.target.value)}
                                    // Logic for Secret: If we assume existing key implies existing secret, we mask it too
                                    placeholder={!!user?.binanceApiKey && !isEditingSecret ? "••••••••••••••••••••••••" : "Enter your Binance API Secret"}
                                    disabled={!!user?.binanceApiKey && !isEditingSecret}
                                    className={cn(
                                        "w-full px-4 py-2.5 pr-20 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-slate-900 dark:text-white",
                                        !!user?.binanceApiKey && !isEditingSecret && "opacity-60 cursor-not-allowed"
                                    )}
                                />
                                <div className="absolute right-2 top-1.5 flex items-center gap-1">
                                    {/* Edit / Cancel Secret Button */}
                                    {user?.binanceApiKey && (
                                        <button
                                            type="button"
                                            onClick={() => {
                                                if (isEditingSecret) {
                                                    setApiSecret('');
                                                    setIsEditingSecret(false);
                                                } else {
                                                    setApiSecret('');
                                                    setIsEditingSecret(true); // Clear only on edit start
                                                }
                                            }}
                                            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors rounded-md hover:bg-slate-200 dark:hover:bg-slate-700"
                                            title={isEditingSecret ? "Cancel Edit" : "Edit Secret"}
                                        >
                                            {isEditingSecret ? <X className="w-4 h-4" /> : <Pencil className="w-4 h-4" />}
                                        </button>
                                    )}

                                    {/* Show/Hide Toggle - only show when there's actual value to show/hide */}
                                    {apiSecret && (
                                        <button
                                            type="button"
                                            onClick={() => setShowApiSecret(!showApiSecret)}
                                            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors rounded-md hover:bg-slate-200 dark:hover:bg-slate-700"
                                            title={showApiSecret ? "Hide Secret" : "Show Secret"}
                                        >
                                            {showApiSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                        </button>
                                    )}
                                </div>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">
                                Stored securely. Leave blank if unchanged.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Submit */}
                <div className="flex flex-col items-end gap-3">
                    <button
                        type="submit"
                        disabled={!isFormValid || updateSettings.isPending}
                        className="px-8 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        {updateSettings.isPending ? (
                            <>
                                <Loader2 className="w-5 h-5 animate-spin" />
                                Saving...
                            </>
                        ) : (
                            'Save Configuration'
                        )}
                    </button>
                    <a
                        href="/connect-guide"
                        className="text-sm text-slate-500 dark:text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors underline underline-offset-2"
                    >
                        Need help? Learn how to connect your Binance API →
                    </a>
                </div>
            </form>
        </div>
    );
}
