package service

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
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
	priceURL   string
}

// NewMarketPriceService creates a new MarketPriceService
func NewMarketPriceService() *MarketPriceService {
	// Use single URL from environment variable, no fallback
	priceURL := os.Getenv("BINANCE_PRICE_URL")

	return &MarketPriceService{
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
		priceURL: priceURL,
	}
}

// FetchRealTimePrices fetches current prices for multiple symbols from Binance Futures
func (s *MarketPriceService) FetchRealTimePrices(ctx context.Context, symbols []string) (map[string]float64, error) {
	if len(symbols) == 0 {
		return make(map[string]float64), nil
	}

	prices := make(map[string]float64)

	// Use configured URL directly
	url := s.priceURL
	if url == "" {
		return nil, fmt.Errorf("BINANCE_PRICE_URL environment variable is not set")
	}

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

	// Create a map for quick lookup: Normalized -> Original(s)
	// We need to map normalized symbol (BTCUSDT) back to requested symbol (BTC/USDT)
	symbolMap := make(map[string][]string)
	for _, symbol := range symbols {
		// Remove slash and uppercase: "BTC/USDT" -> "BTCUSDT"
		norm := strings.ReplaceAll(strings.ToUpper(symbol), "/", "")
		symbolMap[norm] = append(symbolMap[norm], symbol)
	}

	// Extract prices for requested symbols
	for _, ticker := range tickers {
		if originals, ok := symbolMap[ticker.Symbol]; ok {
			var price float64
			_, err := fmt.Sscanf(ticker.Price, "%f", &price)
			if err != nil {
				continue
			}

			// Store price for all variations requested (e.g. both BTC/USDT and BTCUSDT)
			for _, original := range originals {
				prices[original] = price
			}
		}
	}

	// Check if we got all requested symbols
	if len(prices) != len(symbols) {
		missing := []string{}
		for _, symbol := range symbols {
			if _, ok := prices[symbol]; !ok {
				missing = append(missing, symbol)
			}
		}
		// Return found prices and error listing missing ones
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
