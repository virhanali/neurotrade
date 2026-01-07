import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Position, Trade, DashboardStats } from '@/types';

export function usePositions() {
    return useQuery<Position[]>({
        queryKey: ['positions'],
        queryFn: () => api.getPositions(),
        staleTime: 1000 * 10, // 10 seconds
        refetchInterval: 1000 * 30, // Refresh every 30s
    });
}

export function useTradeHistory(limit: number = 50) {
    return useQuery<Trade[]>({
        queryKey: ['trades', limit],
        queryFn: () => api.getTradeHistory(limit),
        staleTime: 1000 * 60, // 1 minute
    });
}

export function useDashboardStats() {
    return useQuery<DashboardStats>({
        queryKey: ['stats'],
        queryFn: () => api.getDashboardStats(),
        staleTime: 1000 * 60, // 1 minute
        refetchInterval: 1000 * 60, // Refresh every minute
    });
}
