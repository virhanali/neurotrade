package domain

import (
	"context"

	"github.com/google/uuid"
)

// FeedbackData represents the data sent to Python for ML learning
type FeedbackData struct {
	Symbol  string           `json:"symbol"`
	Outcome string           `json:"outcome"` // WIN or LOSS
	PnL     float64          `json:"pnl"`
	Metrics *ScreenerMetrics `json:"metrics,omitempty"`
}

// AIService defines the interface for AI analysis operations
type AIService interface {
	// AnalyzeMarket calls the Python Engine to analyze market and generate signals
	// mode: "SCALPER" for M15 aggressive trading, "INVESTOR" for H1 trend following
	AnalyzeMarket(ctx context.Context, balance float64, mode string) ([]*AISignalResponse, error)

	// GetWebSocketPrices fetches real-time prices from Python's WebSocket cache
	GetWebSocketPrices(ctx context.Context, symbols []string) (map[string]float64, error)

	// SendFeedback sends trade outcome to Python ML engine for learning
	SendFeedback(ctx context.Context, feedback *FeedbackData) error

	// ExecuteEntry executes a real entry order via Python Engine with SL/TP/Trailing
	ExecuteEntry(ctx context.Context, params *EntryParams) (*ExecutionResult, error)

	// ExecuteClose executes a real close order via Python Engine
	ExecuteClose(ctx context.Context, symbol, side string, quantity float64, apiKey, apiSecret string) (*ExecutionResult, error)

	// GetRealBalance fetches real wallet balance from Python Engine
	GetRealBalance(ctx context.Context, apiKey, apiSecret string) (float64, error)

	// GetAIAnalytics fetches AI behavior analytics from Python Engine
	GetAIAnalytics(ctx context.Context) (map[string]interface{}, error)

	// HasOpenPosition checks if a symbol has an open position on Binance
	// Returns (hasPosition bool, error)
	HasOpenPosition(ctx context.Context, symbol string, apiKey string, apiSecret string) (bool, error)

	// BatchHasOpenPositions checks positions for multiple symbols in a single call (Phase 2)
	// Returns map[symbol]hasPosition
	BatchHasOpenPositions(ctx context.Context, symbols []string, apiKey string, apiSecret string) (map[string]bool, error)
}

// EntryParams contains all parameters for executing an entry order
type EntryParams struct {
	Symbol           string
	Side             string
	AmountUSDT       float64
	Leverage         int
	APIKey           string
	APISecret        string
	SLPrice          float64 // Stop Loss price (0 = disabled)
	TPPrice          float64 // Take Profit price (0 = disabled)
	TrailingCallback float64 // Trailing stop callback rate in % (0 = disabled, e.g., 1.0 = 1%)
}

// ExecutionResult represents the result of a real trade execution
type ExecutionResult struct {
	Status          string  `json:"status"`
	OrderID         string  `json:"orderId"`
	AvgPrice        float64 `json:"avgPrice"`
	ExecutedQty     float64 `json:"executedQty"`
	SLOrderID       string  `json:"slOrderId,omitempty"`
	TPOrderID       string  `json:"tpOrderId,omitempty"`
	TrailingOrderID string  `json:"trailingOrderId,omitempty"`
}

// TradingService defines the interface for core trading logic
type TradingService interface {
	ProcessMarketScan(ctx context.Context, balance float64, mode string) error
	CloseAllPositions(ctx context.Context, userID uuid.UUID) error
	ClosePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID, isAdmin bool) error
	ApprovePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID) error
	DeclinePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID) error
}
