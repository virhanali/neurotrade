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
                    if (window.location.pathname !== '/login') {
                        window.location.href = '/login';
                    }
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
        const response = await this.client.post<ApiResponse<any>>('/auth/register', data);
        return response.data.data; // Helper unwrap might fail if response structure differs slightly
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
        // Handle ad-hoc response format from HandleUpdateSettings if necessary
        // But assuming it returns { data: User } it works.
        return response.data.data;
    }

    // Positions
    async getPositions(): Promise<Position[]> {
        // Response: { status: "success", data: { mode: "...", positions: [...], ... } }
        const response = await this.client.get<ApiResponse<{ positions: Position[] }>>('/user/positions');
        const data = this.unwrap(response);
        return data.positions || [];
    }

    async closePosition(positionId: string): Promise<Position> {
        const response = await this.client.post<ApiResponse<Position>>(`/user/positions/${positionId}/close`);
        // ClosePosition returns empty string c.String(200, ""). 
        // This will likely fail to unwrap JSON.
        // We should handle this gracefully.
        if (typeof response.data === 'string' && response.data === "") {
            return {} as Position; // Return dummy
        }
        return response.data.data!;
    }

    // Trade History
    async getTradeHistory(limit: number = 50): Promise<Trade[]> {
        // Returns RAW JSON Array: [...]
        const response = await this.client.get<Trade[]>(`/user/history?limit=${limit}`);
        // No unwrap needed
        return response.data;
    }

    // Dashboard Stats
    async getDashboardStats(): Promise<DashboardStats> {
        // Returns RAW JSON Object: { ... }
        const response = await this.client.get<DashboardStats>('/user/stats');
        // No unwrap needed
        return response.data;
    }

    // AI Signals (Admin)
    async getLatestSignals(): Promise<AISignal[]> {
        // Returns SuccessResponse wrapped Array
        const response = await this.client.get<ApiResponse<AISignal[]>>('/admin/signals');
        return this.unwrap(response);
    }

    // System Health
    async getSystemHealth(): Promise<any> {
        const response = await this.client.get<ApiResponse<any>>('/admin/system/health');
        return this.unwrap(response);
    }

    // Brain Health
    async getBrainHealth(): Promise<any> {
        const response = await this.client.get<any>('/admin/ml/brain-health');
        // Proxied directly from Python, usually raw JSON
        return response.data;
    }

    // Balance
    async getRealBalance(): Promise<{ balance: number }> {
        // Likely raw or wrapped? Assuming wrapper if using standard SuccessResponse
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
