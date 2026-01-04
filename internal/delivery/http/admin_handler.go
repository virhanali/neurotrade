package http

import (
	"context"
	"fmt"
	"html/template"
	"io"
	"net/http"
	"sort"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/labstack/echo/v4"

	"neurotrade/internal/delivery/http/dto"
	"neurotrade/internal/domain"
	"neurotrade/internal/utils"
)

// MarketScanScheduler defines the interface for market scan scheduler
type MarketScanScheduler interface {
	SetMode(mode string)
	GetMode() string
}

// AdminHandler handles admin-related requests
type AdminHandler struct {
	db           *pgxpool.Pool
	scheduler    MarketScanScheduler
	signalRepo   domain.SignalRepository
	positionRepo domain.PaperPositionRepository
	templates    *template.Template
}

// NewAdminHandler creates a new AdminHandler
func NewAdminHandler(db *pgxpool.Pool, scheduler MarketScanScheduler, signalRepo domain.SignalRepository, positionRepo domain.PaperPositionRepository, templates *template.Template) *AdminHandler {
	return &AdminHandler{
		db:           db,
		scheduler:    scheduler,
		signalRepo:   signalRepo,
		positionRepo: positionRepo,
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
	statusText := "Healthy"
	statusColor := "text-emerald-600 dark:text-emerald-400"
	dotColor := "bg-emerald-500"

	if err := h.db.Ping(ctx); err != nil {
		statusText = "Unhealthy"
		statusColor = "text-rose-600 dark:text-rose-400"
		dotColor = "bg-rose-500"
	}

	// Get current time in WIB
	loc := utils.GetLocation()
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

// GetLatestScanResults returns the latest scan results formatted as HTML for HTMX
func (h *AdminHandler) GetLatestScanResults(c echo.Context) error {
	ctx := c.Request().Context()
	signals, err := h.signalRepo.GetRecent(ctx, 50)
	if err != nil {
		return c.HTML(http.StatusInternalServerError, fmt.Sprintf("<div class='text-red-500'>Error loading signals: %v</div>", err))
	}

	// Pre-fetch PnL dollar values from paper_positions for all signals in one query
	// Build a map of signal_id -> pnl dollar
	pnlMap := make(map[string]float64)
	if len(signals) > 0 {
		var signalIDs []uuid.UUID
		for _, s := range signals {
			signalIDs = append(signalIDs, s.ID)
		}

		if h.positionRepo != nil {
			idMap, err := h.positionRepo.GetPnLBySignalIDs(ctx, signalIDs)
			if err == nil {
				for id, val := range idMap {
					pnlMap[id.String()] = val
				}
			}
		}
	}

	var viewModels []dto.SignalViewModel
	loc := utils.GetLocation()

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

		// 4. Determine Result from REAL signal data
		isRunning := false
		res := ""
		resColor := "bg-slate-50 text-slate-700 dark:bg-slate-800/50 dark:text-slate-400 border-slate-200 dark:border-slate-700"
		var pnlVal, pnlDollar float64

		// Use actual ReviewResult from signal
		if signal.ReviewResult != nil {
			switch *signal.ReviewResult {
			case "WIN":
				res = "WIN"
				resColor = "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800"
			case "LOSS":
				res = "LOSS"
				resColor = "bg-rose-50 text-rose-700 dark:bg-rose-900/20 dark:text-rose-400 border-rose-200 dark:border-rose-800"
			case "FLOATING":
				isRunning = true
			default:
				isRunning = true
			}
		} else {
			// No review result yet = still running/pending
			isRunning = true
		}

		// Use actual ReviewPnL (percentage) from signal
		if signal.ReviewPnL != nil {
			pnlVal = *signal.ReviewPnL
		}

		// Use actual PnL dollar from paper_positions
		if pnl, exists := pnlMap[signal.ID.String()]; exists {
			pnlDollar = pnl
		}

		viewModels = append(viewModels, dto.SignalViewModel{
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

	// Sort: Running signals first, then Finished.
	// Within groups, original time order (DESC) is preserved by Stable sort.
	sort.SliceStable(viewModels, func(i, j int) bool {
		if viewModels[i].IsRunning && !viewModels[j].IsRunning {
			return true
		}
		if !viewModels[i].IsRunning && viewModels[j].IsRunning {
			return false
		}
		return false
	})

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

// GetBrainHealth proxies the request to the Python engine
// GET /api/admin/ml/brain-health
func (h *AdminHandler) GetBrainHealth(c echo.Context) error {
	url := "http://python-engine:5000/ml/brain-health"
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
