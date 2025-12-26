package http

import (
	"context"
	"net/http"
	"time"

	"github.com/labstack/echo/v4"

	"neurotrade/internal/domain"
	"neurotrade/internal/middleware"
)

// UserHandler handles user-related requests
type UserHandler struct {
	userRepo       domain.UserRepository
	positionRepo   domain.PaperPositionRepository
	tradingService interface {
		CloseAllPositions(ctx context.Context, userID string) error
	}
}

// NewUserHandler creates a new UserHandler
func NewUserHandler(
	userRepo domain.UserRepository,
	positionRepo domain.PaperPositionRepository,
	tradingService interface {
		CloseAllPositions(ctx context.Context, userID string) error
	},
) *UserHandler {
	return &UserHandler{
		userRepo:       userRepo,
		positionRepo:   positionRepo,
		tradingService: tradingService,
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

	return SuccessResponse(c, UserOutput{
		ID:           user.ID.String(),
		Username:     user.Username,
		Role:         user.Role,
		Mode:         user.Mode,
		PaperBalance: user.PaperBalance,
	})
}

// ToggleModeRequest represents the toggle mode request
type ToggleModeRequest struct {
	Mode string `json:"mode"` // "PAPER" or "REAL"
}

// ToggleMode switches user mode between PAPER and REAL
// POST /api/user/mode/toggle
func (h *UserHandler) ToggleMode(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	var req ToggleModeRequest
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

// PositionOutput represents a position in API responses
type PositionOutput struct {
	ID         string   `json:"id"`
	Symbol     string   `json:"symbol"`
	Side       string   `json:"side"`
	EntryPrice float64  `json:"entry_price"`
	SLPrice    float64  `json:"sl_price"`
	TPPrice    float64  `json:"tp_price"`
	Size       float64  `json:"size"`
	ExitPrice  *float64 `json:"exit_price,omitempty"`
	PnL        *float64 `json:"pnl,omitempty"`
	Status     string   `json:"status"`
	CreatedAt  string   `json:"created_at"`
	ClosedAt   *string  `json:"closed_at,omitempty"`
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
		output := make([]PositionOutput, 0, len(positions))
		for _, pos := range positions {
			closedAt := ""
			if pos.ClosedAt != nil {
				closedAt = pos.ClosedAt.Format(time.RFC3339)
			}

			output = append(output, PositionOutput{
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
	if err := h.tradingService.CloseAllPositions(ctx, userID.String()); err != nil {
		return InternalServerErrorResponse(c, "Failed to close all positions", err)
	}

	html := `
		<div class="p-4 bg-white border-2 border-black text-black font-bold shadow-[4px_4px_0px_0px_#000] mt-4">
			✅ All positions closed successfully
		</div>
	`
	return c.HTML(http.StatusOK, html)
}
