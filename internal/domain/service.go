package domain

import "context"

// AIService defines the interface for AI analysis operations
type AIService interface {
	// AnalyzeMarket calls the Python Engine to analyze market and generate signals
	AnalyzeMarket(ctx context.Context, balance float64) ([]*AISignalResponse, error)
}
