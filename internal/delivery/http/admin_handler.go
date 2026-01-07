package http

import (
	"context"
	"io"
	"net/http"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/labstack/echo/v4"

	"neurotrade/internal/domain"
)

// MarketScanScheduler defines the interface for market scan scheduler
type MarketScanScheduler interface {
	GetMode() string
}

// AdminHandler handles admin-related requests
type AdminHandler struct {
	db              *pgxpool.Pool
	scheduler       MarketScanScheduler
	signalRepo      domain.SignalRepository
	positionRepo    domain.PositionRepository
	pythonEngineURL string
}

// NewAdminHandler creates a new admin handler
func NewAdminHandler(db *pgxpool.Pool, scheduler MarketScanScheduler, signalRepo domain.SignalRepository, positionRepo domain.PositionRepository, pythonEngineURL string) *AdminHandler {
	return &AdminHandler{
		db:              db,
		scheduler:       scheduler,
		signalRepo:      signalRepo,
		positionRepo:    positionRepo,
		pythonEngineURL: pythonEngineURL,
	}
}

// StrategyPreset represents a strategy preset
type StrategyPreset struct {
	ID           int    `json:"id"`
	Name         string `json:"name"`
	SystemPrompt string `json:"system_prompt"`
	IsActive     bool   `json:"is_active"`
}

// GetStrategies returns all strategy presets
// GET /api/admin/strategies
func (h *AdminHandler) GetStrategies(c echo.Context) error {
	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	query := `
		SELECT id, name, system_prompt, is_active
		FROM strategy_presets
		ORDER BY id ASC
	`

	rows, err := h.db.Query(ctx, query)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to fetch strategies", err)
	}
	defer rows.Close()

	var strategies []StrategyPreset
	for rows.Next() {
		var s StrategyPreset
		if err := rows.Scan(&s.ID, &s.Name, &s.SystemPrompt, &s.IsActive); err != nil {
			return InternalServerErrorResponse(c, "Failed to scan strategy", err)
		}
		strategies = append(strategies, s)
	}

	if err := rows.Err(); err != nil {
		return InternalServerErrorResponse(c, "Error iterating strategies", err)
	}

	return SuccessResponse(c, map[string]interface{}{
		"strategies": strategies,
		"count":      len(strategies),
	})
}

// SetActiveStrategyRequest represents the request to set active strategy
type SetActiveStrategyRequest struct {
	PresetID int `json:"preset_id"`
}

// SetActiveStrategy sets a strategy as active and deactivates others
// PUT /api/admin/strategies/active
func (h *AdminHandler) SetActiveStrategy(c echo.Context) error {
	var presetID int

	// Try to get from form data first (HTMX sends form-urlencoded)
	if formValue := c.FormValue("preset_id"); formValue != "" {
		var err error
		presetID, err = strconv.Atoi(formValue)
		if err != nil {
			return c.HTML(http.StatusBadRequest, `
				<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
					[ERROR] Invalid preset_id format
				</div>
			`)
		}
	} else {
		// Fallback to JSON binding
		var req SetActiveStrategyRequest
		if err := c.Bind(&req); err != nil {
			return c.HTML(http.StatusBadRequest, `
				<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
					[ERROR] Invalid request payload
				</div>
			`)
		}
		presetID = req.PresetID
	}

	if presetID <= 0 {
		return c.HTML(http.StatusBadRequest, `
			<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
				[ERROR] Invalid preset_id
			</div>
		`)
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Start transaction
	tx, err := h.db.Begin(ctx)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to start transaction", err)
	}
	defer tx.Rollback(ctx)

	// Deactivate all strategies
	_, err = tx.Exec(ctx, "UPDATE strategy_presets SET is_active = false")
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to deactivate strategies", err)
	}

	// Activate selected strategy
	result, err := tx.Exec(ctx, "UPDATE strategy_presets SET is_active = true WHERE id = $1", presetID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to activate strategy", err)
	}

	rowsAffected := result.RowsAffected()
	if rowsAffected == 0 {
		return NotFoundResponse(c, "Strategy preset not found")
	}

	// Commit transaction
	if err := tx.Commit(ctx); err != nil {
		return InternalServerErrorResponse(c, "Failed to commit transaction", err)
	}

	html := `
		<div class="p-4 bg-[#51cf66] border-2 border-black text-black font-bold shadow-[4px_4px_0px_0px_#000]">
			[OK] Strategy updated successfully
		</div>
	`
	return c.HTML(http.StatusOK, html)
}

// SystemHealthResponse represents system health status
type SystemHealthResponse struct {
	Status    string                 `json:"status"`
	Timestamp string                 `json:"timestamp"`
	Services  map[string]interface{} `json:"services"`
}

// GetSystemHealth returns system health check
// GET /api/admin/system/health
func (h *AdminHandler) GetSystemHealth(c echo.Context) error {
	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Check PostgreSQL
	dbStatus := "online"
	if err := h.db.Ping(ctx); err != nil {
		dbStatus = "degraded"
	}

	// Check API (implicit if we are here)
	apiStatus := "online"

	// Check AI Engine (optional, could be added later via health check to python service)
	aiStatus := "online"

	return SuccessResponse(c, map[string]interface{}{
		"status":     "healthy",
		"timestamp":  time.Now().Format(time.RFC3339),
		"db_status":  dbStatus,
		"api_status": apiStatus,
		"ai_status":  aiStatus,
	})
}

// GetStatistics returns admin dashboard statistics
// GET /api/admin/statistics
func (h *AdminHandler) GetStatistics(c echo.Context) error {
	ctx, cancel := context.WithTimeout(c.Request().Context(), 10*time.Second)
	defer cancel()

	stats := make(map[string]interface{})

	// Total users
	var totalUsers int
	if err := h.db.QueryRow(ctx, "SELECT COUNT(*) FROM users").Scan(&totalUsers); err == nil {
		stats["total_users"] = totalUsers
	}

	// Total signals
	var totalSignals int
	if err := h.db.QueryRow(ctx, "SELECT COUNT(*) FROM signals").Scan(&totalSignals); err == nil {
		stats["total_signals"] = totalSignals
	}

	// Signal statistics
	var pendingSignals, executedSignals int
	h.db.QueryRow(ctx, "SELECT COUNT(*) FROM signals WHERE status = 'PENDING'").Scan(&pendingSignals)
	h.db.QueryRow(ctx, "SELECT COUNT(*) FROM signals WHERE status = 'EXECUTED'").Scan(&executedSignals)

	stats["signals"] = map[string]interface{}{
		"pending":  pendingSignals,
		"executed": executedSignals,
	}

	// Position statistics
	var openPositions, closedWin, closedLoss int
	h.db.QueryRow(ctx, "SELECT COUNT(*) FROM paper_positions WHERE status = 'OPEN'").Scan(&openPositions)
	h.db.QueryRow(ctx, "SELECT COUNT(*) FROM paper_positions WHERE status = 'CLOSED_WIN'").Scan(&closedWin)
	h.db.QueryRow(ctx, "SELECT COUNT(*) FROM paper_positions WHERE status = 'CLOSED_LOSS'").Scan(&closedLoss)

	stats["positions"] = map[string]interface{}{
		"open":        openPositions,
		"closed_win":  closedWin,
		"closed_loss": closedLoss,
	}

	// Total PnL
	var totalPnL float64
	h.db.QueryRow(ctx, "SELECT COALESCE(SUM(pnl), 0) FROM paper_positions WHERE pnl IS NOT NULL").Scan(&totalPnL)
	stats["total_pnl"] = totalPnL

	return SuccessResponse(c, stats)
}

// GetLatestScanResults returns the latest scan results formatted as JSON
// GET /api/admin/signals
func (h *AdminHandler) GetLatestScanResults(c echo.Context) error {
	ctx := c.Request().Context()
	signals, err := h.signalRepo.GetRecent(ctx, 50)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to load signals", err)
	}

	// Pre-fetch PnL dollar values from paper_positions for all signals in one query
	metricsMap := make(map[string]domain.MetricResult)
	if len(signals) > 0 {
		var signalIDs []uuid.UUID
		for _, s := range signals {
			signalIDs = append(signalIDs, s.ID)
		}

		if h.positionRepo != nil {
			idMap, err := h.positionRepo.GetPnLBySignalIDs(ctx, signalIDs)
			if err == nil {
				for id, val := range idMap {
					metricsMap[id.String()] = val
				}
			}
		}
	}

	var response []map[string]interface{}

	for _, signal := range signals {
		// Calculate PnL if available
		var pnlVal float64
		if metrics, exists := metricsMap[signal.ID.String()]; exists {
			pnlVal = metrics.PnL
		}

		// Determine result
		result := "PENDING"
		if signal.ReviewResult != nil {
			result = *signal.ReviewResult
		}

		response = append(response, map[string]interface{}{
			"id":               signal.ID.String(),
			"symbol":           signal.Symbol,
			"type":             "CRYPTO",
			"signal":           signal.Type, // LONG/SHORT
			"confidence":       signal.Confidence,
			"reasoning":        signal.Reasoning,
			"recommendation":   "EXECUTE",
			"result":           result,
			"mlWinProbability": float64(signal.Confidence) / 100.0,
			"createdAt":        signal.CreatedAt.Format(time.RFC3339),
			"pnl":              pnlVal,
		})
	}

	return SuccessResponse(c, response)
}

// GetBrainHealth proxies the request to the Python engine
// GET /api/admin/ml/brain-health
func (h *AdminHandler) GetBrainHealth(c echo.Context) error {
	url := h.pythonEngineURL + "/ml/brain-health"
	resp, err := http.Get(url)
	if err != nil {
		c.Logger().Errorf("Failed to proxy to ML: %v", err)
		return c.JSON(http.StatusServiceUnavailable, map[string]string{"error": "ML Service Unavailable", "details": err.Error()})
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to read ML response"})
	}

	return c.Blob(resp.StatusCode, "application/json", body)
}
