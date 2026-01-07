import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { User, UpdateSettingsRequest } from '@/types';

export function useUser() {
    return useQuery<User>({
        queryKey: ['user'],
        queryFn: () => api.getCurrentUser(),
        staleTime: 1000 * 60 * 5, // 5 minutes
        retry: 1,
    });
}

export function useUpdateSettings() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: UpdateSettingsRequest) => api.updateSettings(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['user'] });
        },
    });
}

export function useRefreshBalance() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: () => api.refreshRealBalance(),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['user'] });
        },
    });
}
