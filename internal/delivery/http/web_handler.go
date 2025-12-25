package http

import (
	"context"
	"fmt"
	"html/template"
	"net/http"

	"neurotrade/internal/domain"
	"neurotrade/internal/middleware"

	"github.com/google/uuid"
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
}

func NewWebHandler(
	templates *template.Template,
	userRepo domain.UserRepository,
	positionRepo domain.PaperPositionRepository,
	strategyRepo interface{}, // Placeholder for now (not implemented yet)
	marketPriceSvc MarketPriceService,
) *WebHandler {
	return &WebHandler{
		templates:      templates,
		userRepo:       userRepo,
		positionRepo:   positionRepo,
		marketPriceSvc: marketPriceSvc,
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
		// TODO: Load strategies when StrategyRepository is implemented
		// For now, pass empty slice
		data["Strategies"] = []interface{}{}

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
				<td colspan="8" class="py-4 text-center text-rose-400">
					❌ Authentication required
				</td>
			</tr>
		`)
	}

	// Get all user positions and filter for open ones
	allPositions, err := h.positionRepo.GetByUserID(c.Request().Context(), userID)
	if err != nil {
		return c.HTML(http.StatusInternalServerError, `
			<tr>
				<td colspan="8" class="py-4 text-center text-rose-400">
					❌ Error loading positions
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
				<td colspan="8" class="py-8 text-center text-slate-500">
					No active positions
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
		pnlClass := "text-slate-400"
		pnlSign := ""

		if pos.Side == "BUY" {
			pnl = ((currentPrice - pos.EntryPrice) / pos.EntryPrice) * 100
		} else {
			pnl = ((pos.EntryPrice - currentPrice) / pos.EntryPrice) * 100
		}

		if pnl > 0 {
			pnlClass = "profit"
			pnlSign = "+"
		} else if pnl < 0 {
			pnlClass = "loss"
		}

		sideClass := "text-emerald-400"
		sideEmoji := "🟢"
		if pos.Side == "SELL" {
			sideClass = "text-rose-400"
			sideEmoji = "🔴"
		}

		html += fmt.Sprintf(`
			<tr class="border-b border-terminal-border hover:bg-terminal-bg transition-colors">
				<td class="py-3 px-4 font-semibold text-slate-200">%s</td>
				<td class="py-3 px-4 %s font-semibold">%s %s</td>
				<td class="py-3 px-4 text-slate-300">$%.4f</td>
				<td class="py-3 px-4 text-slate-300">$%.4f</td>
				<td class="py-3 px-4 text-slate-300">$%.4f</td>
				<td class="py-3 px-4 text-slate-300">$%.4f</td>
				<td class="py-3 px-4 font-bold %s">%s%.2f%%</td>
				<td class="py-3 px-4">
					<button
						hx-post="/api/user/positions/%s/close"
						hx-confirm="Close this position?"
						hx-target="closest tr"
						hx-swap="outerHTML"
						class="px-3 py-1 bg-rose-600 hover:bg-rose-700 text-white text-sm rounded transition duration-200"
					>
						❌ Close
					</button>
				</td>
			</tr>
		`,
			pos.Symbol,
			sideClass, sideEmoji, pos.Side,
			pos.EntryPrice,
			currentPrice,
			pos.SLPrice,
			pos.TPPrice,
			pnlClass, pnlSign, pnl,
			pos.ID,
		)
	}

	return c.HTML(http.StatusOK, html)
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

	// Calculate win rate (placeholder for now)
	winRate := 0.0

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
