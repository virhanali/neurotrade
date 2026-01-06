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

// ExecuteEntry executes a real entry order via Python Engine
func (pb *PythonBridge) ExecuteEntry(ctx context.Context, symbol, side string, amountUSDT float64, leverage int) (*domain.ExecutionResult, error) {
	reqBody := map[string]interface{}{
		"symbol":      symbol,
		"side":        side,
		"amount_usdt": amountUSDT,
		"leverage":    leverage,
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
func (pb *PythonBridge) ExecuteClose(ctx context.Context, symbol, side string, quantity float64) (*domain.ExecutionResult, error) {
	reqBody := map[string]interface{}{
		"symbol":   symbol,
		"side":     side,
		"quantity": quantity,
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
