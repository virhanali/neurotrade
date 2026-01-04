package http

import (
	"strings"

	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"

	custommiddleware "neurotrade/internal/middleware"
)

// RouterConfig holds all dependencies for routing
type RouterConfig struct {
	AuthHandler  *AuthHandler
	UserHandler  *UserHandler
	AdminHandler *AdminHandler
}

// SetupRoutes configures all HTTP routes
func SetupRoutes(e *echo.Echo, config *RouterConfig) {
	// Middleware
	e.Use(middleware.LoggerWithConfig(middleware.LoggerConfig{
		Skipper: func(c echo.Context) bool {
			// Skip logging for high-frequency polling endpoints to reduce noise
			path := c.Request().URL.Path
			// Exact match or contains for polling endpoints
			if strings.HasSuffix(path, "/api/user/positions/html") {
				return true
			}
			if strings.HasSuffix(path, "/api/admin/market-scan/results") {
				return true
			}
			if path == "/health" || path == "/api/admin/system/health" {
				return true
			}
			return false
		},
	}))
	e.Use(middleware.Recover())
	e.Use(middleware.CORS())
	e.Use(middleware.RequestID())
	e.Use(middleware.Secure())

	// Root route is handled by WebHandler (RegisterWebRoutes)
	/*
		e.GET("/", func(c echo.Context) error {
			return SuccessResponse(c, map[string]interface{}{
				"message": "Welcome to NeuroTrade AI",
			})
		})
	*/

	// Health check
	e.GET("/health", func(c echo.Context) error {
		return SuccessResponse(c, map[string]interface{}{
			"status":    "healthy",
			"service":   "neurotrade-api",
			"timestamp": "2025-12-26",
		})
	})

	// API group
	api := e.Group("/api")

	// Auth routes (public)
	auth := api.Group("/auth")
	{
		auth.POST("/login", config.AuthHandler.Login)
		auth.POST("/logout", config.AuthHandler.Logout)
		auth.POST("/register", config.AuthHandler.Register)
	}

	// User routes (protected with AuthMiddleware)
	user := api.Group("/user", custommiddleware.AuthMiddleware)
	{
		user.GET("/me", config.UserHandler.GetMe)
		user.POST("/mode/toggle", config.UserHandler.ToggleMode)
		user.GET("/positions", config.UserHandler.GetPositions)
		user.POST("/panic-button", config.UserHandler.PanicButton)
		user.POST("/positions/:id/close", config.UserHandler.ClosePosition)
		user.POST("/positions/:id/approve", config.UserHandler.ApprovePosition)
		user.POST("/positions/:id/decline", config.UserHandler.DeclinePosition)
		user.POST("/settings/autotrade", config.UserHandler.ToggleAutoTrade)
		user.GET("/analytics/pnl", config.UserHandler.GetAnalyticsPnL)
	}

	// Admin routes (protected with Auth + Admin middleware)
	admin := api.Group("/admin", custommiddleware.AuthMiddleware, custommiddleware.AdminMiddleware)
	{
		admin.GET("/strategies", config.AdminHandler.GetStrategies)
		admin.PUT("/strategies/active", config.AdminHandler.SetActiveStrategy)
		admin.GET("/system/health", config.AdminHandler.GetSystemHealth)
		admin.GET("/statistics", config.AdminHandler.GetStatistics)
		admin.POST("/market-scan/trigger", config.AdminHandler.TriggerMarketScan)
		admin.GET("/market-scan/results", config.AdminHandler.GetLatestScanResults)

	}
}
