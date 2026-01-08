// User Types
export interface User {
    id: string;
    username: string;
    email: string;
    role: 'user' | 'admin' | 'USER' | 'ADMIN';
    mode: 'PAPER' | 'REAL';
    paperBalance: number;
    realBalance: number | null;
    fixedOrderSize: number;
    leverage: number;
    autoTradeEnabled: boolean;
    binanceApiKey?: string;
    createdAt: string;
}

// Position Types
export interface Position {
    id: string;
    symbol: string;
    side: 'LONG' | 'SHORT';
    entryPrice: number;
    currentPrice: number;
    size: number;
    slPrice: number;
    tpPrice: number;
    leverage: number;
    unrealizedPnl: number;
    unrealizedPnlPercent: number;
    pnl?: number;
    exitPrice?: number;
    status: 'PENDING' | 'PENDING_APPROVAL' | 'OPEN' | 'CLOSED_WIN' | 'CLOSED_LOSS' | 'CLOSED_MANUAL';
    createdAt: string;
    closedAt?: string;
}

// Trade History
export interface Trade extends Position {
    realizedPnl: number;
    realizedPnlPercent: number;
    closeReason: 'TP' | 'SL' | 'MANUAL' | 'LIQUIDATION';
}

// AI Signal Types
export interface AISignal {
    id: string;
    symbol: string;
    signal: 'LONG' | 'SHORT' | 'WAIT';
    confidence: number;
    reasoning: string;
    entryPrice?: number;
    stopLoss?: number;
    takeProfit?: number;
    suggestedLeverage?: number;
    whaleSignal?: string;
    whaleConfidence?: number;
    visionVerdict?: string;
    visionConfidence?: number;
    mlWinProbability?: number;
    recommendation: 'EXECUTE' | 'SKIP' | 'WAIT';
    createdAt: string;
    result?: string;
    pnl?: number;
}

// Dashboard Stats
export interface DashboardStats {
    totalTrades: number;
    totalWins: number;
    totalLosses: number;
    winRate: number;
    totalPnl: number;
    todayPnl: number;
    todayPnlPercent: number;
    bestTrade: number;
    worstTrade: number;
}

// Settings Update Request
export interface UpdateSettingsRequest {
    mode?: 'PAPER' | 'REAL';
    fixedOrderSize?: number;
    leverage?: number;
    autoTradeEnabled?: boolean;
    binanceApiKey?: string;
    binanceApiSecret?: string;
}

// API Response Types
// API Response Types
export interface ApiResponse<T> {
    status: 'success' | 'error';
    data: T;
    error?: string;
    message?: string;
}

// Auth Types
export interface LoginRequest {
    username: string;
    password: string;
}

export interface LoginResponse {
    token: string;
    user: User;
}

export interface RegisterRequest {
    username: string;
    email: string;
    password: string;
}
