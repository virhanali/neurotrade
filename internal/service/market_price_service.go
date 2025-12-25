package service

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// PriceData represents the current price for a symbol
type PriceData struct {
	Symbol string
	Price  float64
}

// MarketPriceService fetches real-time prices from Binance
type MarketPriceService struct {
	httpClient *http.Client
	baseURL    string
}

// NewMarketPriceService creates a new MarketPriceService
func NewMarketPriceService() *MarketPriceService {
	return &MarketPriceService{
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
		baseURL: "https://api.binance.com",
	}
}

// FetchRealTimePrices fetches current prices for multiple symbols from Binance
func (s *MarketPriceService) FetchRealTimePrices(ctx context.Context, symbols []string) (map[string]float64, error) {
	if len(symbols) == 0 {
		return make(map[string]float64), nil
	}

	prices := make(map[string]float64)

	// Binance API endpoint for ticker price
	url := fmt.Sprintf("%s/api/v3/ticker/price", s.baseURL)

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch prices from Binance: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Binance API error: status=%d, body=%s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	// Parse response - Binance returns array of all tickers
	var tickers []struct {
		Symbol string `json:"symbol"`
		Price  string `json:"price"`
	}

	if err := json.Unmarshal(body, &tickers); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	// Create a map for quick lookup
	symbolMap := make(map[string]bool)
	for _, symbol := range symbols {
		symbolMap[strings.ToUpper(symbol)] = true
	}

	// Extract prices for requested symbols
	for _, ticker := range tickers {
		if symbolMap[ticker.Symbol] {
			var price float64
			_, err := fmt.Sscanf(ticker.Price, "%f", &price)
			if err != nil {
				continue
			}
			prices[ticker.Symbol] = price
		}
	}

	// Check if we got all requested symbols
	if len(prices) != len(symbols) {
		missing := []string{}
		for _, symbol := range symbols {
			if _, ok := prices[strings.ToUpper(symbol)]; !ok {
				missing = append(missing, symbol)
			}
		}
		return prices, fmt.Errorf("missing prices for symbols: %v", missing)
	}

	return prices, nil
}

// FetchSinglePrice fetches the current price for a single symbol
func (s *MarketPriceService) FetchSinglePrice(ctx context.Context, symbol string) (float64, error) {
	prices, err := s.FetchRealTimePrices(ctx, []string{symbol})
	if err != nil {
		return 0, err
	}

	price, ok := prices[strings.ToUpper(symbol)]
	if !ok {
		return 0, fmt.Errorf("price not found for symbol: %s", symbol)
	}

	return price, nil
}

// GetPrice fetches the current price for a single symbol (alias for FetchSinglePrice)
func (s *MarketPriceService) GetPrice(ctx context.Context, symbol string) (float64, error) {
	return s.FetchSinglePrice(ctx, symbol)
}
