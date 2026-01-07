import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AISignal } from '@/types';

export function useAISignals() {
    return useQuery<AISignal[]>({
        queryKey: ['signals'],
        queryFn: () => api.getLatestSignals(),
        staleTime: 1000 * 5, // 5 seconds
        refetchInterval: 1000 * 10, // Refresh every 10s (same as HTMX)
    });
}

export function useSystemHealth() {
    return useQuery({
        queryKey: ['systemHealth'],
        queryFn: async () => {
            const response = await fetch('/api/admin/system/health');
            return response.json();
        },
        staleTime: 1000 * 10,
        refetchInterval: 1000 * 30, // Refresh every 30s
    });
}

export function useBrainHealth() {
    return useQuery({
        queryKey: ['brainHealth'],
        queryFn: async () => {
            const response = await fetch('/api/admin/ml/brain-health');
            return response.json();
        },
        staleTime: 1000 * 30,
        refetchInterval: 1000 * 60, // Refresh every 60s
    });
}

export function usePnLChart(period: '24h' | '7d' = '24h') {
    return useQuery({
        queryKey: ['pnlChart', period],
        queryFn: async () => {
            const response = await fetch(`/api/user/analytics/pnl?period=${period}`);
            return response.json();
        },
        staleTime: 1000 * 60, // 1 minute
    });
}
