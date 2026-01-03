package http

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/labstack/echo/v4"

	"neurotrade/internal/domain"
	"neurotrade/internal/repository"
)

// MarketScanScheduler defines the interface for market scan scheduler
type MarketScanScheduler interface {
	RunNow() error
	SetMode(mode string)
	GetMode() string
}

// AdminHandler handles admin-related requests
type AdminHandler struct {
	db           *pgxpool.Pool
	scheduler    MarketScanScheduler
	signalRepo   domain.SignalRepository
	settingsRepo *repository.SystemSettingsRepository
}

// NewAdminHandler creates a new AdminHandler
func NewAdminHandler(db *pgxpool.Pool, scheduler MarketScanScheduler, signalRepo domain.SignalRepository, settingsRepo *repository.SystemSettingsRepository) *AdminHandler {
	return &AdminHandler{
		db:           db,
		scheduler:    scheduler,
		signalRepo:   signalRepo,
		settingsRepo: settingsRepo,
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
					❌ Invalid preset_id format
				</div>
			`)
		}
	} else {
		// Fallback to JSON binding
		var req SetActiveStrategyRequest
		if err := c.Bind(&req); err != nil {
			return c.HTML(http.StatusBadRequest, `
				<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
					❌ Invalid request payload
				</div>
			`)
		}
		presetID = req.PresetID
	}

	if presetID <= 0 {
		return c.HTML(http.StatusBadRequest, `
			<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
				❌ Invalid preset_id
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
			✅ Strategy updated successfully
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
	status := "✅ Healthy"
	statusBg := "bg-[#51cf66]"
	if err := h.db.Ping(ctx); err != nil {
		status = "❌ Unhealthy"
		statusBg = "bg-[#ff6b6b]"
	}

	// Get current time in WIB
	loc, _ := time.LoadLocation("Asia/Jakarta")
	timestamp := time.Now().In(loc).Format("15:04:05 WIB")

	html := fmt.Sprintf(`
		<div class="space-y-3">
			<div class="p-4 %s border-2 border-black text-black font-bold shadow-[4px_4px_0px_0px_#000]">
				%s
			</div>
			<div class="p-3 bg-white border-2 border-black text-black font-medium shadow-[2px_2px_0px_0px_#000] text-sm">
				Last checked: %s
			</div>
		</div>
	`, statusBg, status, timestamp)

	return c.HTML(http.StatusOK, html)
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

// TriggerMarketScan triggers an immediate market scan manually
// POST /api/admin/market-scan/trigger
func (h *AdminHandler) TriggerMarketScan(c echo.Context) error {
	if h.scheduler == nil {
		return c.HTML(http.StatusInternalServerError, `
			<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
				❌ Scheduler not available
			</div>
		`)
	}

	// Trigger market scan in background
	go func() {
		if err := h.scheduler.RunNow(); err != nil {
			// Log error but don't block response
			c.Logger().Errorf("Market scan failed: %v", err)
		}
	}()

	// Get current time in WIB
	loc, _ := time.LoadLocation("Asia/Jakarta")
	timestamp := time.Now().In(loc).Format("15:04:05 WIB")

	html := fmt.Sprintf(`
		<div class="space-y-3">
			<div class="p-4 bg-[#51cf66] border-2 border-black text-black font-bold shadow-[4px_4px_0px_0px_#000]">
				✅ Triggered
			</div>
			<div class="p-3 bg-white border-2 border-black text-black font-medium shadow-[2px_2px_0px_0px_#000] text-sm">
				Triggered at: %s
			</div>
		</div>
	`, timestamp)

	return c.HTML(http.StatusOK, html)
}

// GetLatestScanResults returns the latest market scan results
// GET /api/admin/market-scan/results
func (h *AdminHandler) GetLatestScanResults(c echo.Context) error {
	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Get latest 10 signals
	signals, err := h.signalRepo.GetRecent(ctx, 10)
	if err != nil {
		return c.HTML(http.StatusInternalServerError, `
			<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
				❌ Failed to fetch results
			</div>
		`)
	}

	if len(signals) == 0 {
		return c.HTML(http.StatusOK, `
			<div class="p-3 bg-white border-2 border-black text-black text-sm text-center shadow-[2px_2px_0px_0px_#000]">
				📭 No signals yet. Trigger a scan to see results.
			</div>
		`)
	}

	// Get timezone
	loc, _ := time.LoadLocation("Asia/Jakarta")

	// Build HTML
	html := `<div class="space-y-2">`

	for _, signal := range signals {
		// Determine colors based on type and confidence
		sideBg := "bg-[#51cf66]"
		sideText := "text-black"
		sideEmoji := "🟢"
		if signal.Type == "SHORT" {
			sideBg = "bg-[#ff6b6b]"
			sideText = "text-white"
			sideEmoji = "🔴"
		}

		confidenceBg := "bg-gray-100"
		if signal.Confidence >= 80 {
			confidenceBg = "bg-[#51cf66]"
		} else if signal.Confidence >= 60 {
			confidenceBg = "bg-[#ffd43b]"
		}

		timestamp := signal.CreatedAt.In(loc).Format("15:04 WIB")

		// PnL Badge Logic
		pnlBadge := ""
		if signal.ReviewResult != nil {
			res := *signal.ReviewResult
			pnlVal := 0.0
			if signal.ReviewPnL != nil {
				pnlVal = *signal.ReviewPnL // This is price move % (unleveraged)
			}

			// Simulation: Leverage 20x, Margin $30
			leverage := 20.0
			margin := 30.0

			roe := pnlVal * leverage
			pnlDollar := (margin * leverage) * (pnlVal / 100.0)

			resColor := "bg-[#ff6b6b] text-white" // Loss Red by default
			if res == "WIN" || roe > 0 {
				resColor = "bg-[#51cf66] text-black" // Profit Green
			}

			pnlBadge = fmt.Sprintf(`
				<div class="mt-1 flex items-center space-x-1">
					<span class="inline-block %s border-2 border-black px-2 py-0.5 text-xs font-bold shadow-[1px_1px_0px_0px_#000]">
						%s
					</span>
					
					<span class="inline-block %s border-2 border-black px-2 py-0.5 text-xs font-bold shadow-[1px_1px_0px_0px_#000]">
						%.0f%% | $%.2f
					</span>
				</div>
			`, resColor, res, resColor, roe, pnlDollar)
		}

		html += fmt.Sprintf(`
			<div class="bg-white border-2 border-black p-2 shadow-[2px_2px_0px_0px_#000] mb-2">
				<div class="flex flex-col">
					<div class="flex items-center justify-between">
						<div class="flex items-center space-x-2">
							<span class="font-bold text-black text-sm">%s</span>
							<span class="inline-block %s %s border-2 border-black px-2 py-0.5 text-xs font-bold shadow-[1px_1px_0px_0px_#000]">
								%s %s
							</span>
							<span class="inline-block %s border-2 border-black px-2 py-0.5 text-xs font-bold text-black shadow-[1px_1px_0px_0px_#000]">
								%d%%
							</span>
						</div>
						<span class="text-xs text-gray-600">%s</span>
					</div>
					%s
				</div>
			</div>
		`, signal.Symbol, sideBg, sideText, sideEmoji, signal.Type, confidenceBg, signal.Confidence, timestamp, pnlBadge)
	}

	html += `</div>`

	return c.HTML(http.StatusOK, html)
}

// TradingModeResponse represents the trading mode response
type TradingModeResponse struct {
	Mode        string `json:"mode"`
	Description string `json:"description"`
}

// GetTradingMode returns the current trading mode
// GET /api/admin/trading-mode
func (h *AdminHandler) GetTradingMode(c echo.Context) error {
	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Get from database via settings repo
	mode := "SCALPER" // default
	if h.settingsRepo != nil {
		if dbMode, err := h.settingsRepo.GetTradingMode(ctx); err == nil {
			mode = dbMode
		}
	}

	// If scheduler is available, sync with its current mode
	if h.scheduler != nil {
		schedulerMode := h.scheduler.GetMode()
		if schedulerMode != mode {
			// Sync scheduler with database
			h.scheduler.SetMode(mode)
		}
	}

	description := "M15 Mean Reversion (Ping-Pong)"
	if mode == "INVESTOR" {
		description = "H1 Trend Following"
	}

	return SuccessResponse(c, TradingModeResponse{
		Mode:        mode,
		Description: description,
	})
}

// SetTradingModeRequest represents the request to set trading mode
type SetTradingModeRequest struct {
	Mode string `json:"mode" form:"mode"`
}

// SetTradingMode updates the trading mode
// PUT /api/admin/trading-mode
func (h *AdminHandler) SetTradingMode(c echo.Context) error {
	var mode string

	// Try to get from form data first (HTMX sends form-urlencoded)
	if formValue := c.FormValue("mode"); formValue != "" {
		mode = formValue
	} else {
		// Fallback to JSON binding
		var req SetTradingModeRequest
		if err := c.Bind(&req); err != nil {
			return c.HTML(http.StatusBadRequest, `
				<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
					❌ Invalid request payload
				</div>
			`)
		}
		mode = req.Mode
	}

	// Validate mode
	if mode != "SCALPER" && mode != "INVESTOR" {
		return c.HTML(http.StatusBadRequest, fmt.Sprintf(`
			<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
				❌ Invalid mode: %s (must be SCALPER or INVESTOR)
			</div>
		`, mode))
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Save to database
	if h.settingsRepo != nil {
		if err := h.settingsRepo.SetTradingMode(ctx, mode); err != nil {
			return c.HTML(http.StatusInternalServerError, fmt.Sprintf(`
				<div class="p-4 bg-[#ff6b6b] border-2 border-black text-white font-bold shadow-[4px_4px_0px_0px_#000]">
					❌ Failed to save: %s
				</div>
			`, err.Error()))
		}
	}

	// Update scheduler mode in real-time
	if h.scheduler != nil {
		h.scheduler.SetMode(mode)
	}

	// Get description
	description := "M15 Mean Reversion (Ping-Pong)"
	emoji := "⚡"
	if mode == "INVESTOR" {
		description = "H1 Trend Following"
		emoji = "📈"
	}

	html := fmt.Sprintf(`
		<div class="space-y-3">
			<div class="p-4 bg-[#51cf66] border-2 border-black text-black font-bold shadow-[4px_4px_0px_0px_#000]">
				✅ Mode updated to %s %s
			</div>
			<div class="p-3 bg-white border-2 border-black text-black font-medium shadow-[2px_2px_0px_0px_#000] text-sm">
				Strategy: %s
			</div>
		</div>
	`, mode, emoji, description)

	return c.HTML(http.StatusOK, html)
}
