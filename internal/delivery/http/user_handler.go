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

	// Optimization: Return cached balance immediately (instant).
	// Trigger background refresh for REAL mode users to keep cache fresh.
	if user.Mode == domain.ModeReal && user.BinanceAPIKey != "" {
		go func(u *domain.User) {
			bgCtx, bgCancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer bgCancel()

			realBal, err := h.aiService.GetRealBalance(bgCtx, u.BinanceAPIKey, u.BinanceAPISecret)
			if err != nil {
				log.Printf("[WARN] Background balance fetch failed for %s: %v", u.Username, err)
				return
			}

			// SAFETY: Only update if we got a valid positive balance
			// This prevents overwriting real data with 0 due to API errors
			if realBal > 0 {
				dbCtx, dbCancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer dbCancel()
				if err := h.userRepo.UpdateRealBalance(dbCtx, u.ID, realBal); err != nil {
					log.Printf("[WARN] Failed to update cached balance: %v", err)
				} else {
					log.Printf("[OK] Updated cached balance for %s: $%.2f", u.Username, realBal)
				}
			} else {
				log.Printf("[WARN] Got zero balance from Binance for %s, skipping update", u.Username)
			}
		}(user)
	}

	maskedKey := ""
	if len(user.BinanceAPIKey) > 4 {
		maskedKey = "..." + user.BinanceAPIKey[len(user.BinanceAPIKey)-4:]
	} else if len(user.BinanceAPIKey) > 0 {
		maskedKey = "***"
	}

	return SuccessResponse(c, dto.UserOutput{
		ID:               user.ID.String(),
		Username:         user.Username,
		Role:             user.Role,
		Mode:             user.Mode,
		PaperBalance:     user.PaperBalance,
		RealBalance:      user.RealBalanceCache,
		FixedOrderSize:   user.FixedOrderSize,
		Leverage:         user.Leverage,
		AutoTradeEnabled: user.IsAutoTradeEnabled,
		BinanceAPIKey:    maskedKey,
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

	// Fetch ALL active positions from DB
	// Currently the DB does not distinguish between REAL/PAPER in the positions table (legacy schema).
	// So we return all positions stored.
	positions, err := h.positionRepo.GetByUserID(ctx, userID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get positions", err)
	}

	// Collect symbols for OPEN positions to fetch current prices
	openSymbols := make([]string, 0)
	for _, pos := range positions {
		if pos.Status == domain.StatusOpen {
			openSymbols = append(openSymbols, pos.Symbol)
		}
	}

	// Fetch current prices - try WebSocket first, fallback to REST
	var currentPrices map[string]float64
	if len(openSymbols) > 0 {
		// 1. Try WebSocket cache (real-time, instant)
		currentPrices, err = h.aiService.GetWebSocketPrices(ctx, openSymbols)

		// 2. Fallback: If WS empty/failed, use REST API via Python
		if err != nil || len(currentPrices) == 0 {
			log.Println("[WARN] WebSocket prices empty, using REST fallback")
			currentPrices = make(map[string]float64)
			// Use MarketPriceService if available, or create inline REST call
			// For now, prices will be 0 but position data still shows
		}
	}

	// Convert to output format with enriched real-time data
	output := make([]dto.PositionOutput, 0, len(positions))
	for _, pos := range positions {
		closedAt := ""
		if pos.ClosedAt != nil {
			closedAt = pos.ClosedAt.Format(time.RFC3339)
		}

		// Calculate unrealized PnL for OPEN positions
		var currentPrice, unrealizedPnl, unrealizedPnlPercent float64
		if pos.Status == domain.StatusOpen {
			if price, ok := currentPrices[pos.Symbol]; ok && price > 0 {
				currentPrice = price
				// Calculate PnL based on side
				if pos.Side == "LONG" {
					unrealizedPnl = (currentPrice - pos.EntryPrice) * pos.Size
				} else { // SHORT
					unrealizedPnl = (pos.EntryPrice - currentPrice) * pos.Size
				}
				// Calculate percentage (with leverage, like Binance)
				if pos.EntryPrice > 0 {
					var rawPercent float64
					if pos.Side == "LONG" {
						rawPercent = ((currentPrice - pos.EntryPrice) / pos.EntryPrice) * 100
					} else {
						rawPercent = ((pos.EntryPrice - currentPrice) / pos.EntryPrice) * 100
					}
					// Apply leverage to match Binance's ROE display
					unrealizedPnlPercent = rawPercent * pos.Leverage
				}
			}
		}

		output = append(output, dto.PositionOutput{
			ID:                   pos.ID.String(),
			Symbol:               pos.Symbol,
			Side:                 pos.Side,
			EntryPrice:           pos.EntryPrice,
			SLPrice:              pos.SLPrice,
			TPPrice:              pos.TPPrice,
			Size:                 pos.Size,
			ExitPrice:            pos.ExitPrice,
			PnL:                  pos.PnL,
			Status:               pos.Status,
			CreatedAt:            pos.CreatedAt.Format(time.RFC3339),
			ClosedAt:             &closedAt,
			Leverage:             pos.Leverage,
			CurrentPrice:         currentPrice,
			UnrealizedPnl:        unrealizedPnl,
			UnrealizedPnlPercent: unrealizedPnlPercent,
		})
	}

	return SuccessResponse(c, map[string]interface{}{
		"mode":      user.Mode,
		"positions": output,
		"count":     len(output),
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

// GetTradeHistory returns closed positions for the user
// GET /api/user/history
func (h *UserHandler) GetTradeHistory(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Get closed positions (full Position objects)
	positions, err := h.positionRepo.GetClosedPositions(ctx, userID, 100)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get trade history", err)
	}

	// Convert to output format
	output := make([]map[string]interface{}, 0, len(positions))
	for _, pos := range positions {
		closedAt := ""
		if pos.ClosedAt != nil {
			closedAt = pos.ClosedAt.Format(time.RFC3339)
		}

		pnl := 0.0
		pnlPercent := 0.0
		if pos.PnL != nil {
			pnl = *pos.PnL
		}
		if pos.PnLPercent != nil {
			pnlPercent = *pos.PnLPercent
		}

		closeReason := "MANUAL"
		if pos.ClosedBy != nil {
			closeReason = *pos.ClosedBy
		}

		output = append(output, map[string]interface{}{
			"id":                   pos.ID.String(),
			"symbol":               pos.Symbol,
			"side":                 pos.Side,
			"entryPrice":           pos.EntryPrice,
			"currentPrice":         pos.ExitPrice,
			"quantity":             pos.Size,
			"margin":               pos.Size,
			"leverage":             pos.Leverage,
			"realizedPnl":          pnl,
			"realizedPnlPercent":   pnlPercent,
			"unrealizedPnl":        0,
			"unrealizedPnlPercent": 0,
			"takeProfit":           pos.TPPrice,
			"stopLoss":             pos.SLPrice,
			"status":               pos.Status,
			"mode":                 "PAPER",
			"closeReason":          closeReason,
			"createdAt":            pos.CreatedAt.Format(time.RFC3339),
			"closedAt":             closedAt,
		})
	}

	return c.JSON(http.StatusOK, output)
}

// GetDashboardStats returns trading statistics for the dashboard
// GET /api/user/stats
func (h *UserHandler) GetDashboardStats(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Get closed positions for stats calculation
	positions, err := h.positionRepo.GetClosedPositions(ctx, userID, 1000)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get statistics", err)
	}

	var totalTrades, wins, losses int
	var totalPnl, bestTrade, worstTrade float64
	var todayPnl, todayPnlPercent float64

	startOfDay := time.Now().Truncate(24 * time.Hour)

	for _, pos := range positions {
		pnl := 0.0
		if pos.PnL != nil {
			pnl = *pos.PnL
		}

		totalTrades++
		totalPnl += pnl

		if pnl > 0 {
			wins++
			if pnl > bestTrade {
				bestTrade = pnl
			}
		} else {
			losses++
			if pnl < worstTrade {
				worstTrade = pnl
			}
		}

		// Today's PnL
		if pos.ClosedAt != nil && pos.ClosedAt.After(startOfDay) {
			todayPnl += pnl
		}
	}

	winRate := 0.0
	if totalTrades > 0 {
		winRate = float64(wins) / float64(totalTrades)
	}

	// Get user for paper balance (to calculate today's %)
	user, err := h.userRepo.GetByID(ctx, userID)
	if err == nil && user.PaperBalance > 0 {
		todayPnlPercent = (todayPnl / user.PaperBalance) * 100
	}

	return c.JSON(http.StatusOK, map[string]interface{}{
		"totalTrades":     totalTrades,
		"totalWins":       wins,
		"totalLosses":     losses,
		"winRate":         winRate,
		"totalPnl":        totalPnl,
		"todayPnl":        todayPnl,
		"todayPnlPercent": todayPnlPercent,
		"bestTrade":       bestTrade,
		"worstTrade":      worstTrade,
	})
}

// UpdateSettings updates user settings (mode, margin, leverage, auto-trade)
// POST /api/settings
func (h *UserHandler) UpdateSettings(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	var req struct {
		Mode             string  `json:"mode" form:"mode"`
		FixedOrderSize   float64 `json:"fixedOrderSize" form:"fixed_order_size"`
		Leverage         float64 `json:"leverage" form:"leverage"`
		AutoTradeEnabled *bool   `json:"autoTradeEnabled" form:"auto_trade_enabled"`
		BinanceAPIKey    string  `json:"binanceApiKey" form:"binance_api_key"`
		BinanceAPISecret string  `json:"binanceApiSecret" form:"binance_api_secret"`
	}

	if err := c.Bind(&req); err != nil {
		return BadRequestResponse(c, "Invalid request payload")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	// Get current user
	user, err := h.userRepo.GetByID(ctx, userID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get user", err)
	}

	// Validate mode
	if req.Mode != "" {
		if req.Mode != "PAPER" && req.Mode != "REAL" {
			return BadRequestResponse(c, "Invalid mode. Must be 'PAPER' or 'REAL'")
		}

		// If switching to REAL mode, ensure Binance API keys are configured
		if req.Mode == "REAL" {
			// Check if new keys are being provided in this request, or if existing keys are set
			hasNewKeys := req.BinanceAPIKey != "" && req.BinanceAPISecret != ""
			hasExistingKeys := user.BinanceAPIKey != "" && user.BinanceAPISecret != ""

			if !hasNewKeys && !hasExistingKeys {
				return BadRequestResponse(c, "Cannot switch to REAL mode without Binance API keys. Please configure your API keys first.")
			}
		}

		user.Mode = req.Mode
	}

	// Validate and update settings
	if req.FixedOrderSize > 0 {
		user.FixedOrderSize = req.FixedOrderSize
	}

	if req.Leverage > 0 {
		user.Leverage = req.Leverage
	}

	if req.AutoTradeEnabled != nil {
		user.IsAutoTradeEnabled = *req.AutoTradeEnabled
	}

	// Handle Binance API keys with validation
	log.Printf("[SETTINGS-DEBUG] Received: apiKeyLen=%d, apiSecretLen=%d", len(req.BinanceAPIKey), len(req.BinanceAPISecret))

	if req.BinanceAPIKey != "" && req.BinanceAPISecret != "" {
		// Test the API keys before saving
		log.Printf("[SETTINGS] Validating Binance API keys for user %s...", user.Username)

		testCtx, testCancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer testCancel()

		_, testErr := h.aiService.GetRealBalance(testCtx, req.BinanceAPIKey, req.BinanceAPISecret)
		if testErr != nil {
			log.Printf("[SETTINGS] API key validation failed for user %s: %v", user.Username, testErr)
			return BadRequestResponse(c, "Invalid Binance API keys. Please check your API Key, Secret, IP whitelist, and ensure 'Enable Futures' permission is enabled.")
		}

		log.Printf("[SETTINGS] API keys validated successfully for user %s", user.Username)
		user.BinanceAPIKey = req.BinanceAPIKey
		user.BinanceAPISecret = req.BinanceAPISecret
	}

	user.UpdatedAt = time.Now()

	// Save to database
	if err := h.userRepo.UpdateSettings(ctx, user); err != nil {
		return InternalServerErrorResponse(c, "Failed to save settings", err)
	}

	log.Printf("[SETTINGS] User %s updated: Mode=%s, Margin=%.2f, Leverage=%.0fx, AutoTrade=%v",
		user.Username, user.Mode, user.FixedOrderSize, user.Leverage, user.IsAutoTradeEnabled)

	return SuccessResponse(c, map[string]interface{}{
		"success": true,
		"message": "Settings saved successfully",
		"user": map[string]interface{}{
			"mode":             user.Mode,
			"fixedOrderSize":   user.FixedOrderSize,
			"leverage":         user.Leverage,
			"autoTradeEnabled": user.IsAutoTradeEnabled,
		},
	})
}

// GetRealBalance returns the user's real balance (cached or fresh)
// GET /api/user/balance/real
func (h *UserHandler) GetRealBalance(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	user, err := h.userRepo.GetByID(ctx, userID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get user", err)
	}

	bal := 0.0
	if user.RealBalanceCache != nil {
		bal = *user.RealBalanceCache
	}

	return SuccessResponse(c, map[string]interface{}{
		"balance": bal,
	})
}

// RefreshRealBalance forces a fetch of real balance from external service
// POST /api/user/balance/refresh
func (h *UserHandler) RefreshRealBalance(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return UnauthorizedResponse(c, "User not authenticated")
	}

	ctx, cancel := context.WithTimeout(c.Request().Context(), 10*time.Second)
	defer cancel()

	// Get User first to get keys
	user, err := h.userRepo.GetByID(ctx, userID)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to get user", err)
	}

	// Call AI/Trading service to get balance from Binance
	bal, err := h.aiService.GetRealBalance(ctx, user.BinanceAPIKey, user.BinanceAPISecret)
	if err != nil {
		// If fails, return cached if avail, or error
		// return InternalServerErrorResponse(c, "Failed to fetch real balance from exchange", err)
		// For robustness, log error and return 0 or cached
		log.Printf("Failed to refresh balance: %v", err)
		return InternalServerErrorResponse(c, "Failed to refresh balance from exchange", err)
	}

	// Update DB Cache
	if err := h.userRepo.UpdateRealBalance(ctx, userID, bal); err != nil {
		log.Printf("Failed to update real balance cache: %v", err)
	}

	return SuccessResponse(c, map[string]interface{}{
		"balance": bal,
	})
}
