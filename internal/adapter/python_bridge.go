package adapter

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
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
