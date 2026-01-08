import { clsx, type ClassValue } from 'clsx';

export function cn(...inputs: ClassValue[]) {
    return clsx(inputs);
}

export function formatCurrency(value: number, decimals: number = 2): string {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    }).format(value ?? 0);
}

export function formatPercent(value: number, decimals: number = 2): string {
    const safeValue = value ?? 0;
    const sign = safeValue >= 0 ? '+' : '';
    return `${sign}${safeValue.toFixed(decimals)}%`;
}

export function formatNumber(value: number, decimals: number = 2): string {
    return (value ?? 0).toFixed(decimals);
}

export function formatDate(date: string | Date): string {
    return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    }).format(new Date(date));
}

export function getTimeAgo(date: string | Date): string {
    const seconds = Math.floor((new Date().getTime() - new Date(date).getTime()) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

export function getPnlColor(pnl: number): string {
    if (pnl > 0) return 'text-emerald-500';
    if (pnl < 0) return 'text-rose-500';
    return 'text-slate-500';
}

export function getPnlBgColor(pnl: number): string {
    if (pnl > 0) return 'bg-emerald-500/10';
    if (pnl < 0) return 'bg-rose-500/10';
    return 'bg-slate-500/10';
}
