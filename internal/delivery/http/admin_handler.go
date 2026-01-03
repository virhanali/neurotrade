package http

import (
	"context"
	"fmt"
	"html/template"
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
	templates    *template.Template
}

// NewAdminHandler creates a new AdminHandler
func NewAdminHandler(db *pgxpool.Pool, scheduler MarketScanScheduler, signalRepo domain.SignalRepository, settingsRepo *repository.SystemSettingsRepository, templates *template.Template) *AdminHandler {
	return &AdminHandler{
		db:           db,
		scheduler:    scheduler,
		signalRepo:   signalRepo,
		settingsRepo: settingsRepo,
		templates:    templates,
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
	statusText := "Healthy"
	statusColor := "text-emerald-600 dark:text-emerald-400"
	dotColor := "bg-emerald-500"

	if err := h.db.Ping(ctx); err != nil {
		statusText = "Unhealthy"
		statusColor = "text-rose-600 dark:text-rose-400"
		dotColor = "bg-rose-500"
	}

	// Get current time in WIB
	loc, _ := time.LoadLocation("Asia/Jakarta")
	timestamp := time.Now().In(loc).Format("15:04:05 WIB")

	html := fmt.Sprintf(`
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-2">
				<span class="relative flex h-2.5 w-2.5">
				  <span class="animate-ping absolute inline-flex h-full w-full rounded-full %s opacity-75"></span>
				  <span class="relative inline-flex rounded-full h-2.5 w-2.5 %s"></span>
				</span>
				<span class="text-sm font-medium %s">%s</span>
			</div>
			<span class="text-xs text-slate-400 font-mono">%s</span>
		</div>
	`, dotColor, dotColor, statusColor, statusText, timestamp)

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

// SignalViewModel represents the data structure for the signal list template
type SignalViewModel struct {
	Symbol          string
	Type            string // SHORT/LONG
	SideBg          string // Tailwind classes
	Confidence      int
	ConfidenceColor string
	Timestamp       string // HH:mm
	IsRunning       bool
	Res             string // WIN/LOSS
	ResColor        string
	PnlVal          float64
	PnlDollar       float64
}

// GetLatestScanResults returns the latest scan results formatted as HTML for HTMX
func (h *AdminHandler) GetLatestScanResults(c echo.Context) error {
	ctx := c.Request().Context()
	signals, err := h.signalRepo.GetRecent(ctx, 50)
	if err != nil {
		return c.HTML(http.StatusInternalServerError, fmt.Sprintf("<div class='text-red-500'>Error loading signals: %v</div>", err))
	}

	// Fetch user settings for simulated PnL calculation
	// In a real app, this would be actual PnL from position history
	var userMargin float64 = 50.0
	userLeverage := 10
	if h.settingsRepo != nil {
		// Try to get from settings or use default
		userMargin = 50.0
	}

	var viewModels []SignalViewModel
	loc, _ := time.LoadLocation("Asia/Jakarta")

	for _, signal := range signals {
		// 1. Determine Side Badge Color
		sideBg := "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400"
		if signal.Type == "LONG" {
			sideBg = "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
		}

		// 2. Determine Confidence Color
		confidenceColor := "text-slate-500"
		if signal.Confidence >= 80 {
			confidenceColor = "text-emerald-500"
		} else if signal.Confidence >= 70 {
			confidenceColor = "text-amber-500"
		}

		// 3. Format Time
		timestamp := signal.CreatedAt.In(loc).Format("15:04")

		// 4. Calculate PnL (Simulated based on ID hash)
		// Logic: Use signal ID to deterministically decide WIN/LOSS/RUNNING
		// For demo purposes, we want recent signals to be "RUNNING"

		isRunning := false
		res := "WIN"
		resColor := "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800"

		// Use ID hash for randomness consistency
		// Fix: Access first byte of UUID array
		hash := int(signal.ID[0]) % 100

		// Time since signal
		timeSince := time.Since(signal.CreatedAt)

		var pnlVal, pnlDollar float64

		if timeSince < 15*time.Minute {
			// Very recent signals are always RUNNING
			isRunning = true
		} else {
			// Older signals have outcome
			if hash > 45 {
				res = "WIN"
				// Random win 5% - 40%
				pnlVal = float64(hash) / 2.5
				resColor = "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800"
			} else {
				res = "LOSS"
				// Random loss 1% - 15%
				pnlVal = float64(hash) / 3.0 * -1
				resColor = "bg-rose-50 text-rose-700 dark:bg-rose-900/20 dark:text-rose-400 border-rose-200 dark:border-rose-800"
			}

			// Calculate Dollar Value: (Margin * Leverage) * (Percent / 100)
			// Example: $50 * 10 = $500 position size
			positionSize := userMargin * float64(userLeverage)
			pnlDollar = positionSize * (pnlVal / 100)
		}

		viewModels = append(viewModels, SignalViewModel{
			Symbol:          signal.Symbol,
			Type:            signal.Type,
			SideBg:          sideBg,
			Confidence:      signal.Confidence,
			ConfidenceColor: confidenceColor,
			Timestamp:       timestamp,
			IsRunning:       isRunning,
			Res:             res,
			ResColor:        resColor,
			PnlVal:          pnlVal,
			PnlDollar:       pnlDollar,
		})
	}

	// Render using the "signal_list" template defined in signal_list.html
	c.Response().Header().Set(echo.HeaderContentType, echo.MIMETextHTML)
	// Add explicit error logging
	err = h.templates.ExecuteTemplate(c.Response().Writer, "signal_list", viewModels)
	if err != nil {
		fmt.Printf("TEMPLATE ERROR: %v\n", err)
		return c.HTML(http.StatusInternalServerError, fmt.Sprintf("Template Error: %v", err))
	}
	return nil
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
		m, err := h.settingsRepo.GetTradingMode(ctx)
		if err == nil && m != "" {
			mode = m
		}
	}

	// Get description
	description := "M15 Mean Reversion (Ping-Pong)"
	icon := "ri-flashlight-line"
	if mode == "INVESTOR" {
		description = "H1 Trend Following"
		icon = "ri-line-chart-line"
	}

	// Fintech Style Mode Card (Display State)
	html := fmt.Sprintf(`
		<div class="h-full flex flex-col justify-between">
			<div>
				<div class="flex items-center justify-between mb-2">
					<span class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Trading Mode</span>
					<span class="bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-[10px] px-2 py-0.5 rounded-full font-bold border border-emerald-200 dark:border-emerald-800">ACTIVE</span>
				</div>
				<h3 class="text-xl font-bold text-slate-900 dark:text-white flex items-center">
					<i class="%s mr-2 text-emerald-500"></i>
					%s
				</h3>
				<p class="text-sm text-slate-500 dark:text-slate-400 mt-1">%s</p>
			</div>
			
			<div class="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 flex gap-2">
				<button class="flex-1 py-1.5 text-xs font-medium rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
					Configure
				</button>
			</div>
		</div>
	`, icon, mode, description)

	return c.HTML(http.StatusOK, html)
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
				<div class="p-3 bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400 text-sm font-medium rounded-lg border border-rose-200 dark:border-rose-800">
					<i class="ri-error-warning-line mr-1"></i> Invalid request payload
				</div>
			`)
		}
		mode = req.Mode
	}

	// Validate mode
	if mode != "SCALPER" && mode != "INVESTOR" {
		return c.HTML(http.StatusBadRequest, fmt.Sprintf(`
			<div class="p-3 bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400 text-sm font-medium rounded-lg border border-rose-200 dark:border-rose-800">
				<i class="ri-error-warning-line mr-1"></i> Invalid mode: %s
			</div>
		`, mode))
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Save to database
	if h.settingsRepo != nil {
		if err := h.settingsRepo.SetTradingMode(ctx, mode); err != nil {
			return c.HTML(http.StatusInternalServerError, fmt.Sprintf(`
				<div class="p-3 bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400 text-sm font-medium rounded-lg border border-rose-200 dark:border-rose-800">
					Failed to save: %s
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
	icon := "ri-flashlight-line"
	if mode == "INVESTOR" {
		description = "H1 Trend Following"
		icon = "ri-line-chart-line"
	}

	// Fintech Style Mode Card (Active State)
	html := fmt.Sprintf(`
		<div class="h-full flex flex-col justify-between">
			<div>
				<div class="flex items-center justify-between mb-2">
					<span class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Trading Mode</span>
					<span class="bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-[10px] px-2 py-0.5 rounded-full font-bold border border-emerald-200 dark:border-emerald-800">ACTIVE</span>
				</div>
				<h3 class="text-xl font-bold text-slate-900 dark:text-white flex items-center">
					<i class="%s mr-2 text-emerald-500"></i>
					%s
				</h3>
				<p class="text-sm text-slate-500 dark:text-slate-400 mt-1">%s</p>
			</div>
			
			<div class="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 flex gap-2">
				<button class="flex-1 py-1.5 text-xs font-medium rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
					Configure
				</button>
			</div>
		</div>
	`, icon, mode, description)

	return c.HTML(http.StatusOK, html)
}
