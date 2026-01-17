package adapter

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"neurotrade/internal/domain"
)

// PythonBridge implements AIService interface
type PythonBridge struct {
	baseURL    string
	httpClient *http.Client
}

// NewPythonBridge creates a new Python Engine bridge
func NewPythonBridge(baseURL string) domain.AIService {
	return &PythonBridge{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 120 * time.Second, // AI analysis can take time
		},
	}
}

// MarketAnalysisRequest represents the request to Python engine
type MarketAnalysisRequest struct {
	Balance       float64  `json:"balance"`
	Mode          string   `json:"mode"`
	CustomSymbols []string `json:"custom_symbols,omitempty"`
}

// FlexibleTime handles multiple timestamp formats from Python
type FlexibleTime struct {
	time.Time
}

// UnmarshalJSON implements custom JSON unmarshalling for flexible timestamp parsing
func (ft *FlexibleTime) UnmarshalJSON(b []byte) error {
	s := strings.Trim(string(b), "\"")

	// Try multiple timestamp formats
	formats := []string{
		time.RFC3339,
		time.RFC3339Nano,
		"2006-01-02T15:04:05.999999", // Python datetime format without timezone
		"2006-01-02T15:04:05",
		time.DateTime,
	}

	for _, format := range formats {
		if t, err := time.Parse(format, s); err == nil {
			ft.Time = t
			return nil
		}
	}

	return fmt.Errorf("unable to parse timestamp: %s", s)
}

// MarketAnalysisResponse represents the response from Python engine
type MarketAnalysisResponse struct {
	Timestamp             FlexibleTime               `json:"timestamp"`
	BTCContext            map[string]interface{}     `json:"btc_context"`
	OpportunitiesScreened int                        `json:"opportunities_screened"`
	ValidSignals          []*domain.AISignalResponse `json:"valid_signals"`
	ExecutionTimeSeconds  float64                    `json:"execution_time_seconds"`
}

// AnalyzeMarket calls the Python Engine to analyze market and generate signals
// mode: "SCALPER" for M15 aggressive trading, "INVESTOR" for H1 trend following
func (pb *PythonBridge) AnalyzeMarket(ctx context.Context, balance float64, mode string) ([]*domain.AISignalResponse, error) {
	// Default to SCALPER if mode is empty
	if mode == "" {
		mode = "SCALPER"
	}

	// Prepare request
	reqBody := MarketAnalysisRequest{
		Balance: balance,
		Mode:    mode,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	// Create HTTP request
	url := fmt.Sprintf("%s/analyze/market", pb.baseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	// Execute request
	resp, err := pb.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to call Python engine: %w", err)
	}
	defer resp.Body.Close()

	// Check status code first
	if resp.StatusCode != http.StatusOK {
		// Only read body if there's an error to report
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Python engine returned error: status=%d, body=%s", resp.StatusCode, string(body))
	}

	// Decode response directly from stream to save memory
	var analysisResp MarketAnalysisResponse
	if err := json.NewDecoder(resp.Body).Decode(&analysisResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return analysisResp.ValidSignals, nil
}

// HealthCheck checks if the Python engine is healthy
func (pb *PythonBridge) HealthCheck(ctx context.Context) error {
	url := fmt.Sprintf("%s/health", pb.baseURL)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return fmt.Errorf("failed to create health check request: %w", err)
	}

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to check Python engine health: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("Python engine is unhealthy: status=%d", resp.StatusCode)
	}

	return nil
}

// GetWebSocketPrices fetches real-time prices from Python's WebSocket cache
func (pb *PythonBridge) GetWebSocketPrices(ctx context.Context, symbols []string) (map[string]float64, error) {
	// Construct URL with symbols parameter
	url := fmt.Sprintf("%s/prices", pb.baseURL)
	if len(symbols) > 0 {
		params := "?symbols=" + strings.Join(symbols, ",")
		url += params
	}

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create prices request: %w", err)
	}

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch prices from Python engine: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("Python engine prices failed with status: %d", resp.StatusCode)
	}

	// Response structure
	var pricesResp struct {
		Prices    map[string]float64 `json:"prices"`
		Connected bool               `json:"connected"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&pricesResp); err != nil {
		return nil, fmt.Errorf("failed to decode prices response: %w", err)
	}

	if !pricesResp.Connected {
		log.Println("[WARN] Warning: Python WebSocket is disconnected")
	}

	return pricesResp.Prices, nil
}

// SendFeedback sends trade outcome to Python ML engine for learning
func (pb *PythonBridge) SendFeedback(ctx context.Context, feedback *domain.FeedbackData) error {
	// Prepare request body matching Python's FeedbackRequest model
	reqBody := map[string]interface{}{
		"symbol":  feedback.Symbol,
		"outcome": feedback.Outcome,
		"pnl":     feedback.PnL,
		"metrics": map[string]interface{}{},
	}

	// Add metrics if available
	if feedback.Metrics != nil {
		reqBody["metrics"] = map[string]interface{}{
			"adx":              feedback.Metrics.ADX,
			"vol_z_score":      feedback.Metrics.VolZScore,
			"efficiency_ratio": feedback.Metrics.KER,
			"is_squeeze":       feedback.Metrics.IsSqueeze,
			"score":            feedback.Metrics.Score,
			"vol_ratio":        feedback.Metrics.VolRatio,
			"atr_pct":          feedback.Metrics.ATRPercent,
		}
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("failed to marshal feedback request: %w", err)
	}

	// Create HTTP request
	url := fmt.Sprintf("%s/feedback", pb.baseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create feedback request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	// Execute request (non-blocking, fire-and-forget pattern)
	resp, err := pb.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send feedback to Python engine: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("Python engine feedback failed: status=%d, body=%s", resp.StatusCode, string(body))
	}

	log.Printf("[ML] Feedback sent: %s %s (PnL: %.2f%%)", feedback.Symbol, feedback.Outcome, feedback.PnL)
	return nil
}

// ==========================================
// REAL TRADING EXECUTION (v6.0)
// ==========================================

// ExecuteEntry executes a real entry order via Python Engine with SL/TP/Trailing
func (pb *PythonBridge) ExecuteEntry(ctx context.Context, params *domain.EntryParams) (*domain.ExecutionResult, error) {
	reqBody := map[string]interface{}{
		"symbol":            params.Symbol,
		"side":              params.Side,
		"amount_usdt":       params.AmountUSDT,
		"leverage":          params.Leverage,
		"api_key":           params.APIKey,
		"api_secret":        params.APISecret,
		"sl_price":          params.SLPrice,
		"tp_price":          params.TPPrice,
		"trailing_callback": params.TrailingCallback,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal execute entry request: %w", err)
	}

	url := fmt.Sprintf("%s/execute/entry", pb.baseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to call Python execution engine: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Python execution failed: status=%d, body=%s", resp.StatusCode, string(body))
	}

	var result domain.ExecutionResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode execution response: %w", err)
	}

	return &result, nil
}

// ExecuteClose executes a real close order via Python Engine
func (pb *PythonBridge) ExecuteClose(ctx context.Context, symbol, side string, quantity float64, apiKey, apiSecret string) (*domain.ExecutionResult, error) {
	reqBody := map[string]interface{}{
		"symbol":     symbol,
		"side":       side,
		"quantity":   quantity,
		"api_key":    apiKey,
		"api_secret": apiSecret,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal execute close request: %w", err)
	}

	url := fmt.Sprintf("%s/execute/close", pb.baseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to call Python execution engine: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Python execution failed: status=%d, body=%s", resp.StatusCode, string(body))
	}

	var result domain.ExecutionResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode execution response: %w", err)
	}

	return &result, nil
}

// GetRealBalance fetches real wallet balance from Python Engine
func (pb *PythonBridge) GetRealBalance(ctx context.Context, apiKey, apiSecret string) (float64, error) {
	url := fmt.Sprintf("%s/execute/balance", pb.baseURL)

	reqBody := map[string]interface{}{
		"api_key":    apiKey,
		"api_secret": apiSecret,
	}
	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return 0, fmt.Errorf("failed to marshal balance request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		log.Printf("[PythonBridge] Failed to create request: %v", err)
		return 0, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		log.Printf("[PythonBridge] Failed to fetch balance: %v", err)
		return 0, fmt.Errorf("failed to fetch balance: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		log.Printf("[PythonBridge] Balance fetch failed: status=%d, body=%s", resp.StatusCode, string(body))
		return 0, fmt.Errorf("failed to fetch balance: status=%d, body=%s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, fmt.Errorf("failed to read response body: %w", err)
	}

	log.Printf("[PythonBridge] Raw Balance Response: %s", string(body))

	var result struct {
		Total float64 `json:"total"`
		Free  float64 `json:"free"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		log.Printf("[PythonBridge] Failed to decode balance response: %v", err)
		return 0, fmt.Errorf("failed to decode balance response: %w", err)
	}

	log.Printf("[PythonBridge] Balance fetched: total=%.2f, free=%.2f", result.Total, result.Free)
	return result.Total, nil
}

// GetAIAnalytics fetches AI behavior analytics from Python Engine
func (pb *PythonBridge) GetAIAnalytics(ctx context.Context) (map[string]interface{}, error) {
	url := fmt.Sprintf("%s/analytics/ai-behavior", pb.baseURL)

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create analytics request: %w", err)
	}

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch analytics from Python engine: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("Python engine analytics failed with status: %d", resp.StatusCode)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode analytics response: %w", err)
	}

	return result, nil
}

// HasOpenPosition checks Binance for open position via Python Engine
func (pb *PythonBridge) HasOpenPosition(ctx context.Context, symbol string, apiKey string, apiSecret string) (bool, error) {
	type hasPositionRequest struct {
		Symbol    string `json:"symbol"`
		APIKey    string `json:"api_key,omitempty"`
		APISecret string `json:"api_secret,omitempty"`
	}

	reqBody := hasPositionRequest{
		Symbol:    symbol,
		APIKey:    apiKey,
		APISecret: apiSecret,
	}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return false, fmt.Errorf("failed to marshal request: %w", err)
	}

	url := fmt.Sprintf("%s/execute/has-position", pb.baseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonBody))
	if err != nil {
		return false, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		log.Printf("[WARN] HasOpenPosition request failed: %v", err)
		return false, nil
	}
	defer resp.Body.Close()

	var result struct {
		HasPosition bool    `json:"has_position"`
		PositionAmt float64 `json:"position_amt"`
		Source      string  `json:"source"`
		Error       string  `json:"error,omitempty"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		log.Printf("[WARN] HasOpenPosition decode failed: %v", err)
		return false, nil
	}

	if result.Error != "" {
		log.Printf("[WARN] Binance position check error: %s", result.Error)
		return false, nil
	}

	if result.HasPosition {
		log.Printf("[DEDUP] Binance has open position for %s: amount=%.4f (source=%s)",
			symbol, result.PositionAmt, result.Source)
	}

	return result.HasPosition, nil
}

// BatchHasOpenPositions checks positions for multiple symbols in a single call
func (pb *PythonBridge) BatchHasOpenPositions(ctx context.Context, symbols []string, apiKey string, apiSecret string) (map[string]bool, error) {
	type batchRequest struct {
		Symbols   []string `json:"symbols"`
		APIKey    string   `json:"api_key"`
		APISecret string   `json:"api_secret"`
	}

	reqBody := batchRequest{
		Symbols:   symbols,
		APIKey:    apiKey,
		APISecret: apiSecret,
	}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal batch request: %w", err)
	}

	url := fmt.Sprintf("%s/execute/has-positions-batch", pb.baseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := pb.httpClient.Do(req)
	if err != nil {
		log.Printf("[WARN] BatchHasOpenPositions request failed: %v", err)
		return nil, err
	}
	defer resp.Body.Close()

	var result struct {
		Positions    map[string]map[string]interface{} `json:"positions"`
		TotalChecked int                               `json:"total_checked"`
		CacheHits    int                               `json:"cache_hits"`
		RestCalls    int                               `json:"rest_calls"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		log.Printf("[WARN] BatchHasOpenPositions decode failed: %v", err)
		return nil, fmt.Errorf("failed to decode batch response: %w", err)
	}

	positions := make(map[string]bool)
	for symbol, data := range result.Positions {
		hasPosition, ok := data["has_position"].(bool)
		if !ok {
			hasPosition = false
		}
		positions[symbol] = hasPosition
	}

	return positions, nil
}
