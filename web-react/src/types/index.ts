// User Types
export interface User {
    id: string;
    username: string;
    email: string;
    role: 'user' | 'admin' | 'USER' | 'ADMIN';
    mode: 'PAPER' | 'REAL';
    paperBalance: number;
    realBalanceCache: number | null;
    fixedOrderSize: number;
    leverage: number;
    autoTradeEnabled: boolean;
    createdAt: string;
}

// Position Types
export interface Position {
    id: string;
    symbol: string;
    side: 'LONG' | 'SHORT';
    entryPrice: number;
    currentPrice: number;
    quantity: number;
    margin: number;
    leverage: number;
    unrealizedPnl: number;
    unrealizedPnlPercent: number;
    takeProfit: number | null;
    stopLoss: number | null;
    status: 'PENDING' | 'PENDING_APPROVAL' | 'OPEN' | 'CLOSED';
    mode: 'PAPER' | 'REAL';
    createdAt: string;
    closedAt: string | null;
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
