package http

import (
	"context"
	"fmt"
	"html/template"
	"net/http"

	"neurotrade/internal/domain"
	"neurotrade/internal/middleware"

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

// GET / - Redirect to dashboard if logged in, else login
func (h *WebHandler) HandleIndex(c echo.Context) error {
	// Check if user is authenticated via cookie
	cookie, err := c.Cookie("token")
	if err != nil || cookie.Value == "" {
		return c.Redirect(http.StatusFound, "/login")
	}

	return c.Redirect(http.StatusFound, "/dashboard")
}

// GET /login - Render login page
func (h *WebHandler) HandleLogin(c echo.Context) error {
	// If already logged in, redirect to dashboard
	cookie, err := c.Cookie("token")
	if err == nil && cookie.Value != "" {
		return c.Redirect(http.StatusFound, "/dashboard")
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
		SameSite: http.SameSiteStrictMode,
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

	data := map[string]interface{}{
		"User":    user,
		"IsAdmin": user.Role == domain.RoleAdmin,
	}

	// If admin, load system statistics
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
				<td colspan="8" class="py-8 text-center">
					<div class="inline-block bg-[#ff6b6b] border-2 border-black text-white font-bold px-6 py-3 shadow-[4px_4px_0px_0px_#000]">
						❌ Authentication required
					</div>
				</td>
			</tr>
		`)
	}

	// Check if user is admin
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
				<td colspan="8" class="py-8 text-center">
					<div class="inline-block bg-[#ff6b6b] border-2 border-black text-white font-bold px-6 py-3 shadow-[4px_4px_0px_0px_#000]">
						❌ Error loading positions
					</div>
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

	if len(positions) == 0 {
		return c.HTML(http.StatusOK, `
			<tr>
				<td colspan="8" class="py-12 text-center">
					<div class="inline-block bg-white border-2 border-black text-black font-bold px-6 py-3 shadow-[4px_4px_0px_0px_#000]">
						No active positions
					</div>
				</td>
			</tr>
		`)
	}

	// Build HTML rows
	html := ""
	for _, pos := range positions {
		// Get current price
		currentPrice, err := h.marketPriceSvc.GetPrice(c.Request().Context(), pos.Symbol)
		if err != nil {
			currentPrice = pos.EntryPrice // Fallback to entry price
		}

		// Calculate PnL
		pnl := 0.0
		pnlBgClass := "bg-gray-100"
		pnlTextClass := "text-black"
		pnlSign := ""

		if pos.Side == "BUY" {
			pnl = ((currentPrice - pos.EntryPrice) / pos.EntryPrice) * 100
		} else {
			pnl = ((pos.EntryPrice - currentPrice) / pos.EntryPrice) * 100
		}

		if pnl > 0 {
			pnlBgClass = "bg-[#51cf66]"
			pnlTextClass = "text-black"
			pnlSign = "+"
		} else if pnl < 0 {
			pnlBgClass = "bg-[#ff6b6b]"
			pnlTextClass = "text-white"
		}

		sideBgClass := "bg-[#51cf66]"
		sideTextClass := "text-black"
		sideEmoji := "🟢"
		if pos.Side == "SHORT" {
			sideBgClass = "bg-[#ff6b6b]"
			sideTextClass = "text-white"
			sideEmoji = "🔴"
		}

		html += fmt.Sprintf(`
			<tr class="hover:bg-gray-50 transition-colors">
				<td class="py-4 px-6">
					<span class="font-bold text-black text-lg">%s</span>
				</td>
				<td class="py-4 px-6">
					<span class="inline-block %s %s border-2 border-black px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_#000]">
						%s %s
					</span>
				</td>
				<td class="py-4 px-6 font-medium text-black">$%.4f</td>
				<td class="py-4 px-6 font-medium text-black">$%.4f</td>
				<td class="py-4 px-6 font-medium text-black">$%.4f</td>
				<td class="py-4 px-6 font-medium text-black">$%.4f</td>
				<td class="py-4 px-6">
					<span class="inline-block %s %s border-2 border-black px-3 py-2 font-bold shadow-[2px_2px_0px_0px_#000]">
						%s%.2f%%
					</span>
				</td>
				<td class="py-4 px-6">
					<button
						hx-post="/api/user/positions/%s/close"
						hx-confirm="Are you sure you want to CLOSE this position?"
						hx-target="closest tr"
						hx-swap="outerHTML"
						class="bg-[#ff6b6b] border-2 border-black text-white font-bold px-4 py-2 shadow-[4px_4px_0px_0px_#000] hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-none transition-all text-sm uppercase tracking-wide"
					>
						❌ Close
					</button>
				</td>
			</tr>
		`,
			pos.Symbol,
			sideBgClass, sideTextClass, sideEmoji, pos.Side,
			pos.EntryPrice,
			currentPrice,
			pos.SLPrice,
			pos.TPPrice,
			pnlBgClass, pnlTextClass, pnlSign, pnl,
			pos.ID,
		)
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
	// Query all closed positions
	// Depending on repo capabilities, we might need a method GetClosedPositions(ctx)
	// For now, let's assume we need to add it or do a raw query here since this is a specific stats need.
	// Actually, we should check if positionRepo has GetClosedPositions or similar?
	// The interface likely doesn't have it yet.
	// Let's do a raw counting query here for efficiency instead of fetching all closed positions into memory.

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

	return map[string]interface{}{
		"TotalUsers":      totalUsers,
		"TotalSignals":    0, // TODO: Add signal count
		"ActivePositions": activePositions,
		"WinRate":         winRate,
	}, nil
}

// RegisterWebRoutes registers all web routes (HTML pages)
func RegisterWebRoutes(e *echo.Echo, handler *WebHandler, authMiddleware echo.MiddlewareFunc) {
	// Public routes
	e.GET("/", handler.HandleIndex)
	e.GET("/login", handler.HandleLogin)
	e.POST("/login", handler.HandleLoginPost)

	// Protected routes (require authentication)
	e.GET("/dashboard", handler.HandleDashboard, authMiddleware)
	e.GET("/api/user/positions/html", handler.HandlePositionsHTML, authMiddleware)
}
