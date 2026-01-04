package http

import (
	"context"
	"fmt"
	"html/template"
	"net/http"

	"neurotrade/internal/domain"
	"neurotrade/internal/middleware"

	"neurotrade/internal/utils"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/labstack/echo/v4"
	"golang.org/x/crypto/bcrypt"
)

// MarketPriceService interface for fetching market prices
type MarketPriceService interface {
	GetPrice(ctx context.Context, symbol string) (float64, error)
}

type WebHandler struct {
	templates      *template.Template
	userRepo       domain.UserRepository
	positionRepo   domain.PaperPositionRepository
	marketPriceSvc MarketPriceService
	db             *pgxpool.Pool
}

func NewWebHandler(
	templates *template.Template,
	userRepo domain.UserRepository,
	positionRepo domain.PaperPositionRepository,
	db *pgxpool.Pool,
	marketPriceSvc MarketPriceService,
) *WebHandler {
	return &WebHandler{
		templates:      templates,
		userRepo:       userRepo,
		positionRepo:   positionRepo,
		marketPriceSvc: marketPriceSvc,
		db:             db,
	}
}

// validateToken checks if the token is valid (using same logic as middleware)
func (h *WebHandler) validateToken(tokenString string) bool {
	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return []byte(middleware.GetJWTSecret()), nil
	})

	return err == nil && token.Valid
}

// GET / - Redirect to dashboard if logged in, else login
func (h *WebHandler) HandleIndex(c echo.Context) error {
	// Check if user is authenticated via cookie
	cookie, err := c.Cookie("token")
	if err == nil && cookie.Value != "" {
		// Verify token is valid before redirecting
		if h.validateToken(cookie.Value) {
			return c.Redirect(http.StatusFound, "/dashboard")
		}
		// Invalid token? Clear it to prevent loops
		c.SetCookie(&http.Cookie{Name: "token", MaxAge: -1, Path: "/"})
	}

	return c.Redirect(http.StatusFound, "/login")
}

// GET /login - Render login page
func (h *WebHandler) HandleLogin(c echo.Context) error {
	// If already logged in AND no error param, redirect to dashboard
	cookie, err := c.Cookie("token")
	errorParam := c.QueryParam("error")

	if err == nil && cookie.Value != "" && errorParam == "" {
		// Verify token is valid before redirecting
		if h.validateToken(cookie.Value) {
			return c.Redirect(http.StatusFound, "/dashboard")
		}
		// Invalid token? Clear it
		c.SetCookie(&http.Cookie{Name: "token", MaxAge: -1, Path: "/"})
	}

	data := map[string]interface{}{
		"Error": c.QueryParam("error"),
	}

	return h.templates.ExecuteTemplate(c.Response().Writer, "login", data)
}

// POST /login - Handle login form submission
func (h *WebHandler) HandleLoginPost(c echo.Context) error {
	username := c.FormValue("username")
	password := c.FormValue("password")

	// Validate input
	if username == "" || password == "" {
		return c.Redirect(http.StatusFound, "/login?error=Username+and+password+are+required")
	}

	// Get user by username
	ctx := c.Request().Context()
	user, err := h.userRepo.GetByUsername(ctx, username)
	if err != nil {
		return c.Redirect(http.StatusFound, "/login?error=Invalid+credentials")
	}

	// Verify password
	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(password)); err != nil {
		return c.Redirect(http.StatusFound, "/login?error=Invalid+credentials")
	}

	// Generate JWT token
	token, err := middleware.GenerateJWT(user.ID, user.Role)
	if err != nil {
		return c.Redirect(http.StatusFound, "/login?error=Failed+to+generate+token")
	}

	// Set HTTP-only cookie
	cookie := &http.Cookie{
		Name:     "token",
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		Secure:   false, // Set to true in production with HTTPS
		SameSite: http.SameSiteLaxMode,
		MaxAge:   86400, // 24 hours
	}
	c.SetCookie(cookie)

	// Redirect to dashboard
	return c.Redirect(http.StatusFound, "/dashboard")
}

// GET /dashboard - Render dashboard
func (h *WebHandler) HandleDashboard(c echo.Context) error {
	// Get user ID from context (set by AuthMiddleware)
	userID, ok := c.Get("user_id").(uuid.UUID)
	if !ok {
		return c.Redirect(http.StatusFound, "/login?error=Authentication+required")
	}

	// Get user from database
	ctx := c.Request().Context()
	user, err := h.userRepo.GetByID(ctx, userID)
	if err != nil {
		return c.Redirect(http.StatusFound, "/login?error=User+not+found")
	}

	// Fetch user's positions to display (server-side rendering initial state)
	// Or fetching them via HTMX later?
	// The dashboard template likely expects some data or uses HTMX.
	// Looking at `HandlePositionsHTML`, it renders a table.
	// But `PendingPositions` are separate.
	// Let's pass PendingPositions to the template so it can render the "Approval Queue".

	allPositions, err := h.positionRepo.GetByUserID(ctx, userID)
	if err != nil {
		allPositions = []*domain.PaperPosition{}
	}

	var pendingPositions []*domain.PaperPosition
	for _, pos := range allPositions {
		if pos.Status == domain.StatusPositionPendingApproval {
			pendingPositions = append(pendingPositions, pos)
		}
	}

	data := map[string]interface{}{
		"User":             user,
		"IsAdmin":          user.Role == domain.RoleAdmin,
		"PendingPositions": pendingPositions,
	}

	// Calculate today's realized PnL from closed positions
	startOfDay := utils.GetStartOfDay()

	var todayPnL float64
	todayPnL, err = h.positionRepo.GetTodayRealizedPnL(ctx, userID, startOfDay)
	if err != nil {
		todayPnL = 0
		// Log error if needed, but for dashboard display 0 is safe fallback
	}

	// Calculate percentage (relative to paper balance)
	todayPnLPercent := 0.0
	if user.PaperBalance > 0 {
		todayPnLPercent = (todayPnL / user.PaperBalance) * 100
	}

	data["TodayPnL"] = todayPnL
	data["TodayPnLPercent"] = todayPnLPercent

	// If admin, load system statistics and settings
	if user.Role == domain.RoleAdmin {
		// Load strategies from database
		strategies, err := h.loadStrategies(ctx)
		if err == nil {
			data["Strategies"] = strategies
		} else {
			data["Strategies"] = []interface{}{}
		}

		// Load system statistics
		stats, err := h.getSystemStats(c)
		if err == nil {
			data["Stats"] = stats
		}

		// Load current trading mode (Scalper enforced)
		tradingMode := "SCALPER"

		// Legacy DB query removed - Mode is now strictly enforced in Python Engine
		// err = h.db.QueryRow(ctx, `SELECT value FROM system_settings WHERE key = 'trading_mode'`).Scan(&modeValue)

		data["TradingMode"] = tradingMode
	}

	return h.templates.ExecuteTemplate(c.Response().Writer, "dashboard", data)
}

// GET /api/user/positions/html - Return HTML fragment of positions for HTMX
func (h *WebHandler) HandlePositionsHTML(c echo.Context) error {
	// Get user ID from context
	userID, ok := c.Get("user_id").(uuid.UUID)
	if !ok {
		return c.HTML(http.StatusUnauthorized, `
			<tr>
				<td colspan="8" class="p-4 text-center text-sm text-rose-500 bg-rose-50 dark:bg-rose-900/10 rounded-lg m-2">
					<i class="ri-lock-line mr-1"></i> Authentication required
				</td>
			</tr>
		`)
	}

	// Check if user is admin (to see all positions)
	isAdmin := false
	if user, err := h.userRepo.GetByID(c.Request().Context(), userID); err == nil {
		isAdmin = user.Role == domain.RoleAdmin
	}

	var allPositions []*domain.PaperPosition
	var err error

	if isAdmin {
		// Admin sees ALL open positions
		allPositions, err = h.positionRepo.GetOpenPositions(c.Request().Context())
	} else {
		// Regular user sees their own positions
		allPositions, err = h.positionRepo.GetByUserID(c.Request().Context(), userID)
	}

	if err != nil {
		return c.HTML(http.StatusInternalServerError, `
			<tr>
				<td colspan="8" class="p-4 text-center text-sm text-slate-500">
					Error loading positions
				</td>
			</tr>
		`)
	}

	// Filter for open positions only
	var positions []*domain.PaperPosition
	for _, pos := range allPositions {
		if pos.Status == domain.StatusOpen {
			positions = append(positions, pos)
		}
	}

	// Continue to processing

	// Build HTML rows
	html := ""
	for _, pos := range positions {
		// Get current price
		currentPrice, err := h.marketPriceSvc.GetPrice(c.Request().Context(), pos.Symbol)
		if err != nil {
			currentPrice = pos.EntryPrice // Fallback
		}

		// Calculate PnL
		pnlPercent := pos.CalculatePnLPercent(currentPrice)
		pnlValue := pos.CalculateGrossPnL(currentPrice)

		// Colors
		pnlClass := "text-slate-500"
		pnlSign := ""
		if pnlPercent > 0 {
			pnlClass = "text-emerald-600 dark:text-emerald-400"
			pnlSign = "+"
		} else if pnlPercent < 0 {
			pnlClass = "text-rose-600 dark:text-rose-400"
		}

		sideBadgeClass := "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
		if pos.Side == "SHORT" {
			sideBadgeClass = "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400"
		}

		// Adaptive decimal formatting based on price magnitude
		formatPrice := func(price float64) string {
			if price >= 1.0 {
				return fmt.Sprintf("$%.4f", price)
			} else if price >= 0.01 {
				return fmt.Sprintf("$%.5f", price)
			} else {
				return fmt.Sprintf("$%.6f", price)
			}
		}

		entryPriceStr := formatPrice(pos.EntryPrice)
		currentPriceStr := formatPrice(currentPrice)
		tpPriceStr := formatPrice(pos.TPPrice)
		slPriceStr := formatPrice(pos.SLPrice)

		html += fmt.Sprintf(`
			<tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors border-b border-slate-50 dark:border-slate-800/50 last:border-0" data-symbol="%s">
                <td class="py-3 px-6 text-sm text-slate-500 dark:text-slate-400 font-mono">%s</td>
				<td class="py-3 px-6">
					<div class="font-bold text-slate-900 dark:text-white">%s</div>
				</td>
				<td class="py-3 px-6">
					<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold %s">
						%s
					</span>
				</td>
				<td class="py-3 px-6 price-cell text-sm text-slate-600 dark:text-slate-300 font-mono"><span class="price-value">%s</span></td>
				<td class="py-3 px-6 price-cell text-sm text-slate-600 dark:text-slate-300 font-mono"><span class="price-value">%s</span></td>
				<td class="py-3 px-6 text-xs font-mono text-slate-400">
					TP: <span class="text-emerald-500">%s</span><br>
					SL: <span class="text-rose-500">%s</span>
				</td>
				<td class="py-3 px-6 pnl-cell">
					<div class="flex flex-col">
						<span class="pnl-value font-bold text-sm %s">%s$%.2f</span>
						<span class="text-xs %s opacity-80">%s%.2f%%</span>
					</div>
				</td>
				<td class="py-3 px-6 text-right">
					<button
						onclick="showConfirmModal('Close Position', 'Are you sure you want to close %s position? This action cannot be undone.', () => htmx.ajax('POST', '/api/user/positions/%s/close', {target: this.closest('tr'), swap: 'outerHTML'}), 'danger')"
						class="text-xs font-medium bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 px-3 py-1.5 rounded hover:bg-rose-50 hover:border-rose-200 hover:text-rose-600 dark:hover:bg-rose-900/20 dark:hover:border-rose-800 dark:hover:text-rose-400 transition-all"
					>
						Close
					</button>
				</td>
			</tr>
		`,
			pos.Symbol,                       // data-symbol
			pos.CreatedAt.Format("15:04:05"), // Time
			pos.Symbol,
			sideBadgeClass, pos.Side,
			entryPriceStr,
			currentPriceStr,
			tpPriceStr,
			slPriceStr,
			pnlClass, pnlSign, pnlValue,
			pnlClass, pnlSign, pnlPercent,
			pos.Symbol, // For modal message
			pos.ID,     // For close API
		)
	}

	// Return empty state if no positions
	if len(positions) == 0 {
		html = `<tr>
        <td colspan="8" class="p-12 text-center text-sm text-slate-400">
            <div class="flex flex-col items-center justify-center gap-3">
                <i class="ri-pulse-line text-4xl text-slate-300 dark:text-slate-600"></i>
                <span class="font-medium">No active positions</span>
				<span class="text-xs">AI is scanning for opportunities...</span>
            </div>
        </td>
    </tr>`
	}

	return c.HTML(http.StatusOK, html)
}

// Helper: Load strategy presets from database
func (h *WebHandler) loadStrategies(ctx context.Context) ([]StrategyPreset, error) {
	query := `
		SELECT id, name, system_prompt, is_active
		FROM strategy_presets
		ORDER BY id ASC
	`

	rows, err := h.db.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to query strategies: %w", err)
	}
	defer rows.Close()

	var strategies []StrategyPreset
	for rows.Next() {
		var s StrategyPreset
		if err := rows.Scan(&s.ID, &s.Name, &s.SystemPrompt, &s.IsActive); err != nil {
			return nil, fmt.Errorf("failed to scan strategy: %w", err)
		}
		strategies = append(strategies, s)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating strategies: %w", err)
	}

	return strategies, nil
}

// Helper: Get system statistics for admin dashboard
func (h *WebHandler) getSystemStats(c echo.Context) (map[string]interface{}, error) {
	ctx := c.Request().Context()

	// Get total users (just count known users for now - we have at least 1)
	totalUsers := 1 // At least the default user exists

	// Get all open positions across system
	allOpenPositions, err := h.positionRepo.GetOpenPositions(ctx)
	activePositions := 0
	if err == nil {
		activePositions = len(allOpenPositions)
	}

	// Calculate win rate
	// Helper query for efficiency
	var totalClosed, wins int
	err = h.db.QueryRow(ctx, `
		SELECT 
			COUNT(*),
			COUNT(*) FILTER (WHERE pnl > 0)
		FROM paper_positions 
		WHERE status IN ('CLOSED', 'CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
	`).Scan(&totalClosed, &wins)

	winRate := 0.0
	if err == nil && totalClosed > 0 {
		winRate = (float64(wins) / float64(totalClosed)) * 100
	}

	// Calculate Total PnL
	var totalPnL float64
	h.db.QueryRow(ctx, "SELECT COALESCE(SUM(pnl), 0) FROM paper_positions WHERE pnl IS NOT NULL").Scan(&totalPnL)

	// Format PnL
	formattedPnL := fmt.Sprintf("$%.2f", totalPnL)
	if totalPnL < 0 {
		formattedPnL = fmt.Sprintf("-$%.2f", -totalPnL)
	}

	return map[string]interface{}{
		"total_users":         totalUsers,
		"total_signals":       0,
		"active_positions":    activePositions,
		"win_rate":            winRate,
		"total_pnl":           totalPnL,
		"total_pnl_formatted": formattedPnL,
		"WinRate":             winRate, // Keep both casings for compatibility
	}, nil
}

// HandleHistoryHTML renders the table rows for trade history
func (h *WebHandler) HandleHistoryHTML(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return echo.NewHTTPError(http.StatusUnauthorized, "Invalid user")
	}
	ctx := c.Request().Context()

	// Get CLOSED positions
	// We use 50 limit for now
	positions, err := h.positionRepo.GetClosedPositions(ctx, userID, 50)
	if err != nil || len(positions) == 0 {
		return c.HTML(http.StatusOK, `
            <tr>
                <td colspan="8" class="p-12 text-center">
                    <div class="flex flex-col items-center justify-center text-slate-400 dark:text-slate-500">
                        <div class="w-16 h-16 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center mb-4 text-emerald-500/50">
                            <i class="ri-file-list-3-line text-3xl"></i>
                        </div>
                        <p class="text-base font-medium text-slate-900 dark:text-white mb-2">No Trade History Yet</p>
                        <p class="text-sm max-w-sm mx-auto mb-6 text-slate-500">Completed trades will appear here automatically.</p>
                    </div>
                </td>
            </tr>
        `)
	}

	html := ""
	for _, pos := range positions {
		// Calculate PnL style
		pnl := 0.0
		if pos.PnL != nil {
			pnl = *pos.PnL
		}
		pnlPerc := 0.0
		if pos.PnLPercent != nil {
			pnlPerc = *pos.PnLPercent
		}

		pnlClass := "text-slate-500"
		if pnl > 0 {
			pnlClass = "text-emerald-600 dark:text-emerald-400"
		} else if pnl < 0 {
			pnlClass = "text-rose-600 dark:text-rose-400"
		}

		statusClass := "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300"
		if pos.Status == "CLOSED_WIN" {
			statusClass = "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-400"
		} else if pos.Status == "CLOSED_LOSS" {
			statusClass = "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-400"
		}

		exitPriceVal := 0.0
		if pos.ExitPrice != nil {
			exitPriceVal = *pos.ExitPrice
		}

		closedDate := "-"
		if pos.ClosedAt != nil {
			closedDate = pos.ClosedAt.Format("01/02 15:04")
		}

		sideColor := "text-rose-500"
		if pos.Side == "LONG" {
			sideColor = "text-emerald-500"
		}

		html += fmt.Sprintf(`
			<tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors border-b border-slate-50 dark:border-slate-800/50 last:border-0">
				<td class="py-3 px-6 text-xs text-slate-500 dark:text-slate-400 font-mono">%s</td>
				<td class="py-3 px-6 font-bold text-slate-900 dark:text-white">%s</td>
				<td class="py-3 px-6">
					<span class="text-xs font-bold %s">%s</span>
				</td>
				<td class="py-3 px-6 text-xs font-mono">%.4f</td>
				<td class="py-3 px-6 text-xs font-mono">$%.4f</td>
				<td class="py-3 px-6 text-xs font-mono">$%.4f</td>
				<td class="py-3 px-6">
					<div class="flex flex-col">
						<span class="font-bold text-xs %s">$%.2f</span>
						<span class="text-[10px] %s opacity-80">%.2f%%</span>
					</div>
				</td>
				<td class="py-3 px-6 text-right">
					<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium uppercase %s">%s</span>
				</td>
			</tr>
		`,
			closedDate,
			pos.Symbol,
			sideColor, pos.Side,
			pos.Size,
			pos.EntryPrice,
			exitPriceVal,
			pnlClass, pnl,
			pnlClass, pnlPerc,
			statusClass, pos.Status,
		)
	}

	return c.HTML(http.StatusOK, html)
}

// RegisterWebRoutes registers all web routes (HTML pages)
func RegisterWebRoutes(e *echo.Echo, handler *WebHandler, authMiddleware echo.MiddlewareFunc) {
	// Public routes
	e.GET("/", handler.HandleIndex)
	e.GET("/login", handler.HandleLogin)
	e.POST("/login", handler.HandleLoginPost)

	// Protected routes (require authentication)
	e.GET("/dashboard", handler.HandleDashboard, authMiddleware)
	e.GET("/dashboard/:tab", handler.HandleDashboard, authMiddleware)
	e.GET("/api/user/positions/html", handler.HandlePositionsHTML, authMiddleware)
	e.GET("/api/user/history/html", handler.HandleHistoryHTML, authMiddleware)
	e.GET("/api/user/positions/count", handler.HandlePositionsCount, authMiddleware)
}

// HandlePositionsCount returns the count of active positions as a plain string (for HTMX)
func (h *WebHandler) HandlePositionsCount(c echo.Context) error {
	userID, ok := c.Get("user_id").(uuid.UUID)
	if !ok {
		return c.String(http.StatusUnauthorized, "0")
	}

	ctx := c.Request().Context()

	// Check if user is admin
	isAdmin := false
	if user, err := h.userRepo.GetByID(ctx, userID); err == nil {
		isAdmin = user.Role == domain.RoleAdmin
	}

	var count int
	var err error

	if isAdmin {
		var positions []*domain.PaperPosition
		positions, err = h.positionRepo.GetOpenPositions(ctx)
		count = len(positions)
	} else {
		// For regular users, we need to filter open positions from their list
		// Optimization: Add GetOpenPositionsByUserID to repo later
		var positions []*domain.PaperPosition
		positions, err = h.positionRepo.GetByUserID(ctx, userID)
		if err == nil {
			for _, pos := range positions {
				if pos.Status == domain.StatusOpen {
					count++
				}
			}
		}
	}

	if err != nil {
		return c.String(http.StatusOK, "0") // Default to 0 on error
	}

	return c.String(http.StatusOK, fmt.Sprintf("%d", count))
}
