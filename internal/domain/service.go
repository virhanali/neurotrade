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

	// ExecuteEntry executes a real entry order via Python Engine
	ExecuteEntry(ctx context.Context, symbol, side string, amountUSDT float64, leverage int) (*ExecutionResult, error)

	// ExecuteClose executes a real close order via Python Engine
	ExecuteClose(ctx context.Context, symbol, side string, quantity float64) (*ExecutionResult, error)
}

// ExecutionResult represents the result of a real trade execution
type ExecutionResult struct {
	Status      string  `json:"status"`
	OrderID     string  `json:"orderId"`
	AvgPrice    float64 `json:"avgPrice"`
	ExecutedQty float64 `json:"executedQty"`
}

// TradingService defines the interface for core trading logic
type TradingService interface {
	ProcessMarketScan(ctx context.Context, balance float64, mode string) error
	CloseAllPositions(ctx context.Context, userID uuid.UUID) error
	ClosePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID, isAdmin bool) error
	ApprovePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID) error
	DeclinePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID) error
}
