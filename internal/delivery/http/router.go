package http

import (
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
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())
	e.Use(middleware.CORS())
	e.Use(middleware.RequestID())
	e.Use(middleware.Secure())

	// Root route
	e.GET("/", func(c echo.Context) error {
		return SuccessResponse(c, map[string]interface{}{
			"message": "Welcome to NeuroTrade AI - Phase 4 API",
			"version": "0.4.0",
			"endpoints": map[string]string{
				"auth":  "/api/auth/*",
				"user":  "/api/user/*",
				"admin": "/api/admin/*",
			},
		})
	})

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
	}

	// Admin routes (protected with Auth + Admin middleware)
	admin := api.Group("/admin", custommiddleware.AuthMiddleware, custommiddleware.AdminMiddleware)
	{
		admin.GET("/strategies", config.AdminHandler.GetStrategies)
		admin.PUT("/strategies/active", config.AdminHandler.SetActiveStrategy)
		admin.GET("/system/health", config.AdminHandler.GetSystemHealth)
		admin.GET("/statistics", config.AdminHandler.GetStatistics)
		admin.POST("/market-scan/trigger", config.AdminHandler.TriggerMarketScan)
	}
}
