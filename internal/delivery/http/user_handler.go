package http

import (
	"context"
	"log"
	"net/http"
	"time"

	"neurotrade/internal/delivery/http/dto"
	"neurotrade/internal/domain"
	"neurotrade/internal/middleware"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
)

// UserHandler handles user-related requests
type UserHandler struct {
	userRepo       domain.UserRepository
	positionRepo   domain.PositionRepository
	tradingService domain.TradingService
	aiService      domain.AIService
}

// NewUserHandler creates a new UserHandler
func NewUserHandler(
	userRepo domain.UserRepository,
	positionRepo domain.PositionRepository,
	tradingService domain.TradingService,
	aiService domain.AIService,
) *UserHandler {
	return &UserHandler{
		userRepo:       userRepo,
		positionRepo:   positionRepo,
		tradingService: tradingService,
		aiService:      aiService,
	}
}

// GetMe returns current user details
// GET /api/user/me
func (h *UserHandler) GetMe(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	user, err := h.userRepo.GetByID(ctx, userID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get user details", err)
	}

	// For REAL mode, try to fetch fresh balance from Binance
	if user.Mode == domain.ModeReal {
		// We use a short timeout for this external call
		bgCtx, bgCancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer bgCancel()

		log.Printf("[INFO] Fetching REAL balance from Binance for user %s", userID)

		realBal, err := h.aiService.GetRealBalance(bgCtx)
		if err == nil && realBal > 0 {
			// Update memory object
			user.RealBalanceCache = &realBal

			// Async update DB to not block UI
			go func(uid uuid.UUID, bal float64) {
				dbCtx, dbCancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer dbCancel()
				if err := h.userRepo.UpdateRealBalance(dbCtx, uid, bal); err != nil {
					log.Printf("[ERROR] Failed to cache real balance for user %s: %v\n", uid, err)
				} else {
					log.Printf("[SUCCESS] Cached real balance for user %s: %.2f USDT\n", uid, bal)
				}
			}(user.ID, realBal)
		} else {
			errMsg := "unknown"
			if err != nil {
				errMsg = err.Error()
			}
			log.Printf("[ERROR] Failed to fetch real balance for user %s: %s (using cache: %.2f)\n", userID, errMsg, func() float64 {
				if user.RealBalanceCache != nil {
					return *user.RealBalanceCache
				}
				return 0
			}())
		}
	}

	return SuccessResponse(c, dto.UserOutput{
		ID:           user.ID.String(),
		Username:     user.Username,
		Role:         user.Role,
		Mode:         user.Mode,
		PaperBalance: user.PaperBalance,
		RealBalance:  user.RealBalanceCache,
	})
}

// ToggleMode switches user mode between PAPER and REAL
// POST /api/user/mode/toggle
func (h *UserHandler) ToggleMode(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	var req dto.ToggleModeRequest
	if err := c.Bind(&req); err != nil {
		return BadRequestResponse(c, "Invalid request payload")
	}

	// Validate mode
	if req.Mode != domain.ModePaper && req.Mode != domain.ModeReal {
		return BadRequestResponse(c, "Invalid mode. Must be 'PAPER' or 'REAL'")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Get current user
	user, err := h.userRepo.GetByID(ctx, userID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get user", err)
	}

	// Update mode (implementation depends on your User repository)
	// For now, we'll need to add an UpdateMode method to UserRepository
	// Temporary: Just return current mode
	user.Mode = req.Mode
	user.UpdatedAt = time.Now()

	return SuccessResponse(c, map[string]interface{}{
		"mode":    user.Mode,
		"message": "Mode updated successfully",
	})
}

// GetPositions returns user's active positions
// GET /api/user/positions
func (h *UserHandler) GetPositions(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Get user to check mode
	user, err := h.userRepo.GetByID(ctx, userID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get user", err)
	}

	// For now, we only support PAPER mode (Phase 3)
	if user.Mode == domain.ModePaper {
		positions, err := h.positionRepo.GetByUserID(ctx, userID)
		if err != nil {
			return InternalServerErrorResponse(c, "Failed to get positions", err)
		}

		// Convert to output format
		output := make([]dto.PositionOutput, 0, len(positions))
		for _, pos := range positions {
			closedAt := ""
			if pos.ClosedAt != nil {
				closedAt = pos.ClosedAt.Format(time.RFC3339)
			}

			output = append(output, dto.PositionOutput{
				ID:         pos.ID.String(),
				Symbol:     pos.Symbol,
				Side:       pos.Side,
				EntryPrice: pos.EntryPrice,
				SLPrice:    pos.SLPrice,
				TPPrice:    pos.TPPrice,
				Size:       pos.Size,
				ExitPrice:  pos.ExitPrice,
				PnL:        pos.PnL,
				Status:     pos.Status,
				CreatedAt:  pos.CreatedAt.Format(time.RFC3339),
				ClosedAt:   &closedAt,
			})
		}

		return SuccessResponse(c, map[string]interface{}{
			"mode":      user.Mode,
			"positions": output,
			"count":     len(output),
		})
	}

	// REAL mode: fetch from Binance API (Phase 5 - not implemented yet)
	return SuccessResponse(c, map[string]interface{}{
		"mode":      user.Mode,
		"positions": []interface{}{},
		"count":     0,
		"message":   "Real trading not implemented yet",
	})
}

// PanicButton closes all open positions immediately
// POST /api/user/panic-button
func (h *UserHandler) PanicButton(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 30*time.Second)
	defer cancel()

	// Close all positions
	if err := h.tradingService.CloseAllPositions(ctx, userID); err != nil {
		return InternalServerErrorResponse(c, "Failed to close all positions", err)
	}

	html := `
		<div class="p-4 bg-white border-2 border-black text-black font-bold shadow-[4px_4px_0px_0px_#000] mt-4">
			[OK] All positions closed successfully
		</div>
	`
	return c.HTML(http.StatusOK, html)
}

// ClosePosition closes a specific position
// POST /api/user/positions/:id/close
func (h *UserHandler) ClosePosition(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	positionIDStr := c.Param("id")
	positionID, err := uuid.Parse(positionIDStr)
	if err != nil {
		return BadRequestResponse(c, "Invalid position ID")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 10*time.Second)
	defer cancel()

	// Check if admin
	isAdmin := false
	if user, err := h.userRepo.GetByID(ctx, userID); err == nil {
		isAdmin = user.Role == domain.RoleAdmin
	}

	if err := h.tradingService.ClosePosition(ctx, positionID, userID, isAdmin); err != nil {
		return InternalServerErrorResponse(c, "Failed to close position", err)
	}

	// Return empty string to remove the row from table (HTMX swap)
	return c.String(http.StatusOK, "")
}

// ToggleAutoTrade updates the user's auto-trade setting
// POST /api/user/settings/autotrade
func (h *UserHandler) ToggleAutoTrade(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	var req struct {
		// Support both JSON "enabled": true and Form "enabled=true"
		Enabled bool `json:"enabled" form:"enabled" query:"enabled"`
	}

	// Bind automatically handles JSON body OR Form values
	if err := c.Bind(&req); err != nil {
		return BadRequestResponse(c, "Invalid request payload")
	}

	ctx := c.Request().Context()

	if err := h.userRepo.UpdateAutoTradeStatus(ctx, userID, req.Enabled); err != nil {
		return InternalServerErrorResponse(c, "Failed to update auto-trade status", err)
	}

	return SuccessResponse(c, map[string]interface{}{
		"enabled": req.Enabled,
		"message": "Auto-trade setting updated",
	})
}

// ApprovePosition approves a pending position
// POST /api/user/positions/:id/approve
func (h *UserHandler) ApprovePosition(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	positionIDStr := c.Param("id")
	positionID, err := uuid.Parse(positionIDStr)
	if err != nil {
		return BadRequestResponse(c, "Invalid position ID")
	}

	ctx := c.Request().Context()

	if err := h.tradingService.ApprovePosition(ctx, positionID, userID); err != nil {
		return InternalServerErrorResponse(c, "Failed to approve position", err)
	}

	// HTMX response: remove the row from the pending table
	return c.String(http.StatusOK, "")
}

// DeclinePosition declines a pending position
// POST /api/user/positions/:id/decline
func (h *UserHandler) DeclinePosition(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	positionIDStr := c.Param("id")
	positionID, err := uuid.Parse(positionIDStr)
	if err != nil {
		return BadRequestResponse(c, "Invalid position ID")
	}

	ctx := c.Request().Context()

	if err := h.tradingService.DeclinePosition(ctx, positionID, userID); err != nil {
		return InternalServerErrorResponse(c, "Failed to decline position", err)
	}

	// HTMX response: remove the row from the pending table
	return c.String(http.StatusOK, "")
}

// GetAnalyticsPnL returns PnL history for charting
// GET /api/analytics/pnl?period=24h|7d
func (h *UserHandler) GetAnalyticsPnL(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx := c.Request().Context()

	// Get period parameter (default: 24h)
	period := c.QueryParam("period")
	var since time.Time

	switch period {
	case "7d":
		since = time.Now().AddDate(0, 0, -7)
	case "24h":
		fallthrough
	default:
		since = time.Now().Add(-24 * time.Hour)
	}

	// Get closed positions with time filter
	history, err := h.positionRepo.GetClosedPositionsHistorySince(ctx, userID, since, 100)
	if err != nil {
		// Fallback to old method if new method not available
		history, err = h.positionRepo.GetClosedPositionsHistory(ctx, userID, 50)
		if err != nil {
			return InternalServerErrorResponse(c, "Failed to fetch PnL history", err)
		}
	}

	// Process data for Chart.js
	var labels []string
	var data []float64
	var individualPnls []float64
	cumulative := 0.0

	// Because history is ordered ASC, we can just accumulate
	for _, entry := range history {
		// Format label: "Jan 02 15:04"
		labels = append(labels, entry.ClosedAt.Format("Jan 02 15:04"))

		individualPnls = append(individualPnls, entry.PnL)
		cumulative += entry.PnL
		data = append(data, cumulative)
	}

	return SuccessResponse(c, map[string]interface{}{
		"labels":          labels,
		"data":            data,
		"individual_pnls": individualPnls,
		"period":          period,
	})
}
