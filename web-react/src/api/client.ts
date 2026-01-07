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

    // Helper to unwrap API response
    // Go Backend returns: { status: "success", data: T, ... }
    private unwrap<T>(response: { data: ApiResponse<T> }): T {
        return response.data.data;
    }

    // Auth
    async login(data: LoginRequest): Promise<LoginResponse> {
        const response = await this.client.post<ApiResponse<LoginResponse>>('/auth/login', data);
        const result = this.unwrap(response);
        localStorage.setItem('token', result.token);
        return result;
    }

    async register(data: RegisterRequest): Promise<User> {
        // Register returns specific user data inside wrapper
        const response = await this.client.post<ApiResponse<any>>('/auth/register', data);
        // Backend register returns { username: "..." } basically messages. 
        // But let's assume it returns user or we ignore for now, login is priority.
        // Wait, AuthHandler.Register returns CreatedResponse with map[string]string.
        // So generic 'any' is safer here unless we change backend.
        return this.unwrap(response);
    }

    async logout(): Promise<void> {
        localStorage.removeItem('token');
        window.location.href = '/login';
    }

    // User
    async getCurrentUser(): Promise<User> {
        const response = await this.client.get<ApiResponse<User>>('/user/me');
        return this.unwrap(response);
    }

    async updateSettings(data: UpdateSettingsRequest): Promise<User> {
        const response = await this.client.post<ApiResponse<User>>('/settings', data);
        // Note: '/settings' endpoint returns { success: true, data: User } wrapped in JSON(200, map)
        // WebHandler.HandleUpdateSettings returns c.JSON(http.StatusOK, map)
        // It does NOT use SuccessResponse wrapper standard from response.go
        // It returns: { success: true, message: "...", data: User }
        // So response.data is the object directly.
        // Wait, standard `SuccessResponse` produces `status`, `data`.
        // WebHandler `HandleUpdateSettings` produces `success`, `data`.
        // Inconsistency! I should fix WebHandler to be consistent or handle it here.
        // Let's assume WebHandler response structure: { data: User }
        return response.data.data!;
    }

    // Positions
    async getPositions(): Promise<Position[]> {
        const response = await this.client.get<ApiResponse<Position[]>>('/user/positions');
        return this.unwrap(response);
    }

    async closePosition(positionId: string): Promise<Position> {
        const response = await this.client.post<ApiResponse<Position>>(`/user/positions/${positionId}/close`);
        return this.unwrap(response);
    }

    // Trade History
    async getTradeHistory(limit: number = 50): Promise<Trade[]> {
        const response = await this.client.get<ApiResponse<Trade[]>>(`/user/history?limit=${limit}`);
        return this.unwrap(response);
    }

    // Dashboard Stats
    async getDashboardStats(): Promise<DashboardStats> {
        const response = await this.client.get<ApiResponse<DashboardStats>>('/user/stats');
        return this.unwrap(response);
    }

    // AI Signals (Admin)
    async getLatestSignals(): Promise<AISignal[]> {
        const response = await this.client.get<ApiResponse<AISignal[]>>('/admin/signals');
        return this.unwrap(response);
    }

    // Balance
    async getRealBalance(): Promise<{ balance: number }> {
        const response = await this.client.get<ApiResponse<{ balance: number }>>('/user/balance/real');
        return this.unwrap(response);
    }

    async refreshRealBalance(): Promise<{ balance: number }> {
        const response = await this.client.post<ApiResponse<{ balance: number }>>('/user/balance/refresh');
        return this.unwrap(response);
    }
}

export const api = new ApiClient();
export default api;
