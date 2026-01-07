import axios, { type AxiosError, type AxiosInstance } from 'axios';
import type {
    User,
    Position,
    Trade,
    AISignal,
    DashboardStats,
    UpdateSettingsRequest,
    ApiResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest
} from '@/types';

const API_BASE = '/api';

class ApiClient {
    private client: AxiosInstance;

    constructor() {
        this.client = axios.create({
            baseURL: API_BASE,
            headers: {
                'Content-Type': 'application/json',
            },
        });

        // Add token to requests
        this.client.interceptors.request.use((config) => {
            const token = localStorage.getItem('token');
            if (token) {
                config.headers.Authorization = `Bearer ${token}`;
            }
            return config;
        });

        // Handle 401 errors
        this.client.interceptors.response.use(
            (response) => response,
            (error: AxiosError) => {
                if (error.response?.status === 401) {
                    localStorage.removeItem('token');
                    window.location.href = '/login';
                }
                return Promise.reject(error);
            }
        );
    }

    // Auth
    async login(data: LoginRequest): Promise<LoginResponse> {
        const response = await this.client.post<LoginResponse>('/auth/login', data);
        localStorage.setItem('token', response.data.token);
        return response.data;
    }

    async register(data: RegisterRequest): Promise<ApiResponse<User>> {
        const response = await this.client.post<ApiResponse<User>>('/auth/register', data);
        return response.data;
    }

    async logout(): Promise<void> {
        localStorage.removeItem('token');
        window.location.href = '/login';
    }

    // User
    async getCurrentUser(): Promise<User> {
        const response = await this.client.get<User>('/user/me');
        return response.data;
    }

    async updateSettings(data: UpdateSettingsRequest): Promise<ApiResponse<User>> {
        const response = await this.client.post<ApiResponse<User>>('/settings', data);
        return response.data;
    }

    // Positions
    async getPositions(): Promise<Position[]> {
        const response = await this.client.get<Position[]>('/user/positions');
        return response.data;
    }

    async closePosition(positionId: string): Promise<ApiResponse<Position>> {
        const response = await this.client.post<ApiResponse<Position>>(`/user/positions/${positionId}/close`);
        return response.data;
    }

    // Trade History
    async getTradeHistory(limit: number = 50): Promise<Trade[]> {
        const response = await this.client.get<Trade[]>(`/user/history?limit=${limit}`);
        return response.data;
    }

    // Dashboard Stats
    async getDashboardStats(): Promise<DashboardStats> {
        const response = await this.client.get<DashboardStats>('/user/stats');
        return response.data;
    }

    // AI Signals (Admin)
    async getLatestSignals(): Promise<AISignal[]> {
        const response = await this.client.get<AISignal[]>('/admin/signals');
        return response.data;
    }

    // Balance
    async getRealBalance(): Promise<{ balance: number }> {
        const response = await this.client.get<{ balance: number }>('/user/balance/real');
        return response.data;
    }

    async refreshRealBalance(): Promise<{ balance: number }> {
        const response = await this.client.post<{ balance: number }>('/user/balance/refresh');
        return response.data;
    }
}

export const api = new ApiClient();
export default api;
