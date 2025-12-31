package domain

import "context"

// MarketPriceService defines the interface for fetching market prices
type MarketPriceService interface {
	FetchRealTimePrices(ctx context.Context, symbols []string) (map[string]float64, error)
	FetchSinglePrice(ctx context.Context, symbol string) (float64, error)
	GetPrice(ctx context.Context, symbol string) (float64, error)
}
