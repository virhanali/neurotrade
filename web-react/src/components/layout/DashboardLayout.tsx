import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
    LayoutDashboard,
    TrendingUp,
    History,
    Settings,
    LogOut,
    Brain,
    Wallet,
    Sun,
    Moon,
    Activity,
    Shield
} from 'lucide-react';
import { useUser } from '@/hooks/useUser';
import { useTheme } from '@/hooks/useTheme';
import { usePositions } from '@/hooks/usePositions';
import { api } from '@/api/client';
import { cn, formatCurrency } from '@/utils/helpers';

const navItems = [
    { path: '/dashboard', label: 'Overview', icon: LayoutDashboard },
    { path: '/positions', label: 'Live Positions', icon: TrendingUp },
    { path: '/history', label: 'Trade History', icon: History },
    { path: '/settings', label: 'Settings', icon: Settings },
];

export function DashboardLayout() {
    const location = useLocation();
    const queryClient = useQueryClient();
    const { data: user } = useUser();
    const { data: positions } = usePositions();
    const { theme, toggleTheme } = useTheme();

    const balance = user?.mode === 'REAL'
        ? user.realBalanceCache ?? 0
        : user?.paperBalance ?? 0;

    const openPositionsCount = positions?.filter(p => p.status === 'OPEN').length || 0;
    const isAdmin = user?.role === 'admin' || user?.role === 'ADMIN';

    // Build nav items with conditional admin
    const allNavItems = isAdmin
        ? [...navItems, { path: '/admin', label: 'Admin', icon: Shield }]
        : navItems;

    const handleToggleMode = async () => {
        const newMode = user?.mode === 'REAL' ? 'PAPER' : 'REAL';
        if (!confirm(`Switch to ${newMode} trading mode?`)) return;

        try {
            await api.updateSettings({ mode: newMode });

            await queryClient.invalidateQueries({ queryKey: ['user'] });
            await queryClient.invalidateQueries({ queryKey: ['positions'] });
            await queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] });

            window.location.reload();
        } catch (error) {
            console.error('Failed to toggle mode:', error);
            alert('Failed to switch trading mode');
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
            {/* Sidebar */}
            <aside className="fixed left-0 top-0 h-full w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-40">
                {/* Logo */}
                <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-200 dark:border-slate-800">
                    <div className="p-2 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl">
                        <Brain className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h1 className="text-lg font-bold text-slate-900 dark:text-white">NeuroTrade</h1>
                        <p className="text-xs text-slate-500">AI Trading Platform</p>
                    </div>
                </div>

                {/* Balance Card */}
                <div className="mx-4 mt-4 p-4 bg-gradient-to-br from-slate-100 to-slate-50 dark:from-slate-800 dark:to-slate-900 rounded-xl border border-slate-200 dark:border-slate-700">
                    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm mb-1">
                        <Wallet className="w-4 h-4" />
                        <span>Total Equity</span>
                    </div>
                    <div className="flex items-baseline justify-between gap-2">
                        <span className="text-2xl font-bold text-slate-900 dark:text-white">
                            {formatCurrency(balance)}
                        </span>

                        {/* Mode Switcher Button */}
                        <button
                            onClick={handleToggleMode}
                            className={cn(
                                'text-[10px] font-bold px-2 py-1 rounded-lg cursor-pointer transition-all border shadow-sm',
                                user?.mode === 'REAL'
                                    ? 'bg-rose-500 hover:bg-rose-600 text-white border-rose-600'
                                    : 'bg-emerald-500 hover:bg-emerald-600 text-white border-emerald-600'
                            )}
                            title="Click to switch trading mode"
                        >
                            {user?.mode || 'PAPER'}
                        </button>
                    </div>
                </div>

                {/* Navigation */}
                <nav className="mt-6 px-3">
                    {allNavItems.map(({ path, label, icon: Icon }) => (
                        <NavLink
                            key={path}
                            to={path}
                            className={({ isActive }) => cn(
                                'flex items-center gap-3 px-4 py-3 rounded-xl mb-1 transition-all duration-200',
                                isActive
                                    ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 font-medium'
                                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                            )}
                        >
                            <Icon className="w-5 h-5" />
                            <span>{label}</span>
                            {path === '/positions' && openPositionsCount > 0 && (
                                <span className="ml-auto px-2 py-0.5 text-xs font-bold bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400 rounded-full">
                                    {openPositionsCount}
                                </span>
                            )}
                        </NavLink>
                    ))}
                </nav>

                {/* Logout */}
                <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-slate-200 dark:border-slate-800">
                    <button
                        onClick={() => api.logout()}
                        className="flex items-center gap-3 w-full px-4 py-3 rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    >
                        <LogOut className="w-5 h-5" />
                        <span>Logout</span>
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="ml-64 min-h-screen">
                {/* Header */}
                <header className="sticky top-0 z-30 bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border-b border-slate-200 dark:border-slate-800">
                    <div className="px-8 py-4 flex items-center justify-between">
                        <h2 className="text-xl font-bold text-slate-900 dark:text-white capitalize">
                            {location.pathname.replace('/', '') || 'Dashboard'}
                        </h2>

                        {/* Right side actions */}
                        <div className="flex items-center gap-4">
                            {/* Active Positions Badge */}
                            {openPositionsCount > 0 && (
                                <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 dark:bg-emerald-900/20 rounded-full">
                                    <Activity className="w-4 h-4 text-emerald-500 animate-pulse" />
                                    <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
                                        {openPositionsCount} Active
                                    </span>
                                </div>
                            )}

                            {/* Dark Mode Toggle */}
                            <button
                                onClick={toggleTheme}
                                className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                                title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
                            >
                                {theme === 'dark' ? (
                                    <Sun className="w-5 h-5" />
                                ) : (
                                    <Moon className="w-5 h-5" />
                                )}
                            </button>
                        </div>
                    </div>
                </header>

                {/* Page Content */}
                <div className="p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
