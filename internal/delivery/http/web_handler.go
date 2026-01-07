package http

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"time"

	"neurotrade/internal/domain"
	"neurotrade/internal/middleware"

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
	userRepo       domain.UserRepository
	positionRepo   domain.PositionRepository
	marketPriceSvc MarketPriceService
	db             *pgxpool.Pool
}

func NewWebHandler(
	userRepo domain.UserRepository,
	positionRepo domain.PositionRepository,
	db *pgxpool.Pool,
	marketPriceSvc MarketPriceService,
) *WebHandler {
	return &WebHandler{
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
	return c.String(http.StatusOK, "NeuroTrade API is running. Please access the frontend used in development at http://localhost:3000")
}

// GET /login - Render login page
func (h *WebHandler) HandleLogin(c echo.Context) error {
	return c.Redirect(http.StatusTemporaryRedirect, "http://localhost:3000/login")
}

// POST /login - Handle login form submission
func (h *WebHandler) HandleLoginPost(c echo.Context) error {
	return c.JSON(http.StatusBadRequest, map[string]string{"error": "Please use /api/auth/login"})
}

// GET /register - Render register page
func (h *WebHandler) HandleRegister(c echo.Context) error {
	return c.Redirect(http.StatusTemporaryRedirect, "http://localhost:3000/register")
}

// POST /register - Handle register form submission
func (h *WebHandler) HandleRegisterPost(c echo.Context) error {
	username := c.FormValue("username")
	password := c.FormValue("password")
	confirmPassword := c.FormValue("confirm_password")

	// Validate input
	if username == "" || password == "" {
		return c.Redirect(http.StatusFound, "/register?error=Username+and+password+are+required")
	}

	if len(password) < 6 {
		return c.Redirect(http.StatusFound, "/register?error=Password+must+be+at+least+6+characters")
	}

	if password != confirmPassword {
		return c.Redirect(http.StatusFound, "/register?error=Passwords+do+not+match")
	}

	ctx := c.Request().Context()

	// Check if username exists
	existingUser, err := h.userRepo.GetByUsername(ctx, username)
	if err == nil && existingUser != nil {
		return c.Redirect(http.StatusFound, "/register?error=Username+already+taken")
	}

	// Hash password
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return c.Redirect(http.StatusFound, "/register?error=Internal+server+error")
	}

	// Create user
	newUser := &domain.User{
		ID:                 uuid.New(),
		Username:           username,
		PasswordHash:       string(hashedPassword),
		Role:               domain.RoleUser,
		Mode:               domain.ModePaper,
		PaperBalance:       5000.0, // Default Paper Balance
		MaxDailyLoss:       5.0,    // Default 5%
		IsAutoTradeEnabled: false,  // Default disabled
		FixedOrderSize:     1.0,    // Default $1 (MINIMUM for safe testing)
		Leverage:           1.0,    // Default 1x (safe)
		CreatedAt:          time.Now(),
		UpdatedAt:          time.Now(),
	}

	if err := h.userRepo.Create(ctx, newUser); err != nil {
		return c.Redirect(http.StatusFound, "/register?error=Failed+to+create+account")
	}

	// Auto login (Generate Token)
	token, err := middleware.GenerateJWT(newUser.ID, newUser.Role)
	if err != nil {
		// If token fails, just redirect to login
		return c.Redirect(http.StatusFound, "/login?message=Account+created,+please+login")
	}

	// Set Cookie
	cookie := &http.Cookie{
		Name:     "token",
		Value:    token,
		Expires:  time.Now().Add(24 * time.Hour),
		HttpOnly: true,
		Path:     "/",
	}
	c.SetCookie(cookie)

	return c.Redirect(http.StatusFound, "/dashboard")
}

// GET /dashboard - Render dashboard
func (h *WebHandler) HandleDashboard(c echo.Context) error {
	return c.Redirect(http.StatusTemporaryRedirect, "http://localhost:3000/dashboard")
}

// GET /api/user/positions/html - Return HTML fragment for legacy support (Stub)
func (h *WebHandler) HandlePositionsHTML(c echo.Context) error {
	return c.String(http.StatusOK, "Please use React Frontend")
}

// HandleHistoryHTML - Stub
func (h *WebHandler) HandleHistoryHTML(c echo.Context) error {
	return c.String(http.StatusOK, "Please use React Frontend")
}

// RegisterWebRoutes registers all web routes
func RegisterWebRoutes(e *echo.Echo, handler *WebHandler, authMiddleware echo.MiddlewareFunc) {
	// Public routes
	e.GET("/", handler.HandleIndex)
	e.GET("/login", handler.HandleLogin)
	e.POST("/login", handler.HandleLoginPost)
	e.GET("/register", handler.HandleRegister)
	e.POST("/register", handler.HandleRegisterPost)

	// Protected routes (require authentication)
	e.GET("/dashboard", handler.HandleDashboard, authMiddleware)
	e.GET("/dashboard/:tab", handler.HandleDashboard, authMiddleware)
	e.GET("/api/user/positions/html", handler.HandlePositionsHTML, authMiddleware)
	e.GET("/api/user/history/html", handler.HandleHistoryHTML, authMiddleware)
	e.GET("/api/user/positions/count", handler.HandlePositionsCount, authMiddleware)
	e.GET("/api/settings/modal", handler.HandleSettingsModal, authMiddleware)
	e.POST("/api/settings", handler.HandleUpdateSettings, authMiddleware)
}

// HandlePositionsCount returns the count of active positions as a plain string
func (h *WebHandler) HandlePositionsCount(c echo.Context) error {
	userID, ok := c.Get("user_id").(uuid.UUID)
	if !ok {
		return c.String(http.StatusUnauthorized, "0")
	}

	ctx := c.Request().Context()
	isAdmin := false
	if user, err := h.userRepo.GetByID(ctx, userID); err == nil {
		isAdmin = user.Role == domain.RoleAdmin
	}

	var count int
	var err error

	if isAdmin {
		var positions []*domain.Position
		positions, err = h.positionRepo.GetOpenPositions(ctx)
		count = len(positions)
	} else {
		var positions []*domain.Position
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
		return c.String(http.StatusOK, "0")
	}

	return c.String(http.StatusOK, fmt.Sprintf("%d", count))
}

// GET /api/settings/modal - Stub
func (h *WebHandler) HandleSettingsModal(c echo.Context) error {
	return c.String(http.StatusOK, "Please use React Settings Page")
}

type UpdateSettingsRequest struct {
	Mode             string  `json:"mode"`
	FixedOrderSize   float64 `json:"fixedOrderSize"`
	Leverage         float64 `json:"leverage"`
	AutoTradeEnabled bool    `json:"autoTradeEnabled"`
}

// POST /api/settings - Update user settings (JSON Support)
func (h *WebHandler) HandleUpdateSettings(c echo.Context) error {
	userID, ok := c.Get("user_id").(uuid.UUID)
	if !ok {
		return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Unauthorized"})
	}

	// Parse JSON
	var req UpdateSettingsRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request format"})
	}

	// Validate Mode
	if req.Mode != domain.ModePaper && req.Mode != domain.ModeReal {
		req.Mode = domain.ModePaper
	}

	// Validate numeric values
	if req.FixedOrderSize < 1.0 {
		req.FixedOrderSize = 1.0
	}
	if req.Leverage < 1.0 {
		req.Leverage = 1.0
	}

	// Fetch User
	user, err := h.userRepo.GetByID(c.Request().Context(), userID)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to fetch user"})
	}

	// Update Fields
	user.Mode = req.Mode
	user.FixedOrderSize = req.FixedOrderSize
	user.Leverage = req.Leverage
	user.IsAutoTradeEnabled = req.AutoTradeEnabled

	// Safety: Add validation for REAL mode
	if user.Mode == domain.ModeReal {
		if user.Leverage > 125.0 {
			user.Leverage = 125.0 // Binance max
		}
		if user.FixedOrderSize < 1.0 {
			user.FixedOrderSize = 1.0
		}
		log.Printf("[IMPORTANT] User %s switched to REAL TRADING mode", user.Username)
	}

	// Persist
	if err := h.userRepo.UpdateSettings(c.Request().Context(), user); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("Failed to save settings: %v", err)})
	}

	return c.JSON(http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "Settings saved successfully",
		"data":    user,
	})
}
