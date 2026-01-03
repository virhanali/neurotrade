package domain

import "context"

// AIService defines the interface for AI analysis operations
type AIService interface {
	// AnalyzeMarket calls the Python Engine to analyze market and generate signals
	// mode: "SCALPER" for M15 aggressive trading, "INVESTOR" for H1 trend following
	AnalyzeMarket(ctx context.Context, balance float64, mode string) ([]*AISignalResponse, error)

	// GetWebSocketPrices fetches real-time prices from Python's WebSocket cache
	GetWebSocketPrices(ctx context.Context, symbols []string) (map[string]float64, error)
}
