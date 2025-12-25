package http

import (
	"context"
	"time"

	"github.com/labstack/echo/v4"
	"github.com/jackc/pgx/v5/pgxpool"
)

// AdminHandler handles admin-related requests
type AdminHandler struct {
	db *pgxpool.Pool
}

// NewAdminHandler creates a new AdminHandler
func NewAdminHandler(db *pgxpool.Pool) *AdminHandler {
	return &AdminHandler{
		db: db,
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
	var req SetActiveStrategyRequest
	if err := c.Bind(&req); err != nil {
		return BadRequestResponse(c, "Invalid request payload")
	}

	if req.PresetID <= 0 {
		return BadRequestResponse(c, "Invalid preset_id")
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
	result, err := tx.Exec(ctx, "UPDATE strategy_presets SET is_active = true WHERE id = $1", req.PresetID)
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

	return SuccessMessageResponse(c, "Active strategy updated successfully", map[string]interface{}{
		"preset_id": req.PresetID,
	})
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

	services := make(map[string]interface{})

	// Check PostgreSQL
	pgStatus := "healthy"
	if err := h.db.Ping(ctx); err != nil {
		pgStatus = "unhealthy"
		services["postgres"] = map[string]interface{}{
			"status": pgStatus,
			"error":  err.Error(),
		}
	} else {
		services["postgres"] = map[string]interface{}{
			"status": pgStatus,
		}
	}

	// Check Redis (if available in context)
	// For now, we'll skip Redis as it's not critical
	services["redis"] = map[string]interface{}{
		"status": "not_checked",
	}

	// Overall status
	overallStatus := "healthy"
	if pgStatus != "healthy" {
		overallStatus = "degraded"
	}

	return SuccessResponse(c, SystemHealthResponse{
		Status:    overallStatus,
		Timestamp: time.Now().Format(time.RFC3339),
		Services:  services,
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
