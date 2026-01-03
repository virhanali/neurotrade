package main

import (
	"context"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/joho/godotenv"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
	"github.com/robfig/cron/v3"

	"neurotrade/configs"
	"neurotrade/internal/adapter"
	"neurotrade/internal/adapter/telegram"
	"neurotrade/internal/database"
	httpdelivery "neurotrade/internal/delivery/http"
	"neurotrade/internal/infra"
	authmiddleware "neurotrade/internal/middleware"
	"neurotrade/internal/repository"
	"neurotrade/internal/service"
	"neurotrade/internal/usecase"
)

func main() {
	// Load environment variables
	if err := godotenv.Load(); err != nil {
		log.Println("Warning: .env file not found, using environment variables")
	}

	// Load configuration
	cfg := configs.Load()

	// Initialize context
	ctx := context.Background()

	// Initialize database with retry
	var db *pgxpool.Pool
	var err error
	maxRetries := 10
	retryDelay := 5 * time.Second

	for i := 0; i < maxRetries; i++ {
		db, err = infra.NewDatabase(ctx, cfg.Database.URL)
		if err == nil {
			log.Println("✓ Database connected successfully")
			break
		}

		if i < maxRetries-1 {
			log.Printf("Failed to connect to database (attempt %d/%d): %v. Retrying in %v...", i+1, maxRetries, err, retryDelay)
			time.Sleep(retryDelay)
		} else {
			log.Fatalf("Failed to connect to database after %d attempts: %v", maxRetries, err)
		}
	}
	defer db.Close()

	// Run database migrations (auto-create tables if needed)
	if err := database.RunMigrations(db); err != nil {
		log.Fatalf("Failed to run database migrations: %v", err)
	}

	// Initialize repositories
	signalRepo := repository.NewSignalRepository(db)
	userRepo := repository.NewUserRepository(db)
	positionRepo := repository.NewPaperPositionRepository(db)
	settingsRepo := repository.NewSystemSettingsRepository(db)

	// Initialize Telegram notification service (Phase 5)
	telegramBotToken := os.Getenv("TELEGRAM_BOT_TOKEN")
	telegramChatID := os.Getenv("TELEGRAM_CHAT_ID")
	notificationService := telegram.NewNotificationService(telegramBotToken, telegramChatID)
	if telegramBotToken != "" && telegramChatID != "" {
		log.Println("✓ Telegram notifications enabled")
	} else {
		log.Println("⚠️  Telegram notifications disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable)")
	}

	// Initialize AI service (Python Bridge)
	aiService := adapter.NewPythonBridge(cfg.Python.URL)

	// Health check Python engine
	log.Println("Checking Python Engine health...")
	if bridge, ok := aiService.(*adapter.PythonBridge); ok {
		if err := bridge.HealthCheck(ctx); err != nil {
			log.Printf("WARNING: Python Engine is not available: %v", err)
			log.Println("Scheduler will continue, but market scans will fail until Python Engine is running")
		} else {
			log.Println("✓ Python Engine is healthy")
		}
	}

	// Initialize services
	priceService := service.NewMarketPriceService()
	virtualBroker := service.NewVirtualBrokerService(positionRepo, userRepo, priceService, signalRepo, notificationService)
	reviewService := service.NewReviewService(signalRepo, priceService, notificationService)
	bodyguard := service.NewBodyguardService(positionRepo, userRepo, priceService, signalRepo, notificationService, aiService)

	// Initialize trading service
	tradingService := usecase.NewTradingService(
		aiService,
		signalRepo,
		positionRepo,
		userRepo,
		notificationService,
		priceService,
		cfg.Trading.MinConfidence,
	)

	// Load trading mode from database (default: SCALPER if not set)
	tradingMode, err := settingsRepo.GetTradingMode(ctx)
	if err != nil {
		tradingMode = "SCALPER" // Default mode
		log.Printf("⚠️ Trading mode not found in DB, using default: %s", tradingMode)
	} else {
		log.Printf("✓ Trading mode loaded from database: %s", tradingMode)
	}

	// Initialize market scan scheduler
	marketScanScheduler := infra.NewScheduler(tradingService, cfg.Trading.DefaultBalance, tradingMode)
	if err := marketScanScheduler.Start(); err != nil {
		log.Fatalf("Failed to start market scan scheduler: %v", err)
	}
	defer marketScanScheduler.Stop()

	// Initialize Phase 3 cron jobs
	cronScheduler := cron.New(cron.WithSeconds()) // Enable seconds-level scheduling

	// Bodyguard: Fast position check every 10 seconds (Phase 2 - Safety)
	_, err = cronScheduler.AddFunc("*/10 * * * * *", func() {
		ctx := context.Background()
		if err := bodyguard.CheckPositionsFast(ctx); err != nil {
			log.Printf("ERROR: Bodyguard check failed: %v", err)
		}
	})
	if err != nil {
		log.Fatalf("Failed to add bodyguard cron job: %v", err)
	}

	// Virtual Broker: Check positions every 1 minute (backup to Bodyguard)
	_, err = cronScheduler.AddFunc("0 */1 * * * *", func() {
		ctx := context.Background()
		if err := virtualBroker.CheckPositions(ctx); err != nil {
			log.Printf("ERROR: Virtual broker check failed: %v", err)
		}
	})
	if err != nil {
		log.Fatalf("Failed to add virtual broker cron job: %v", err)
	}

	// Review Service: Review signals at minute 5 of every hour
	_, err = cronScheduler.AddFunc("0 5 * * * *", func() {
		ctx := context.Background()
		if err := reviewService.ReviewPastSignals(ctx, 60); err != nil {
			log.Printf("ERROR: Review service failed: %v", err)
		}
	})
	if err != nil {
		log.Fatalf("Failed to add review service cron job: %v", err)
	}

	// Health Check: Verify Python Engine every 6 hours
	_, err = cronScheduler.AddFunc("0 0 */6 * * *", func() {
		log.Println("🏥 Running scheduled health check...")
		if bridge, ok := aiService.(*adapter.PythonBridge); ok {
			if err := bridge.HealthCheck(context.Background()); err != nil {
				log.Printf("⚠️ HEALTH CHECK FAILED: Python Engine is not available: %v", err)
			} else {
				log.Println("✅ Health check passed: Python Engine is healthy")
			}
		}
	})
	if err != nil {
		log.Fatalf("Failed to add health check cron job: %v", err)
	}

	// Start Phase 3 cron scheduler
	cronScheduler.Start()
	defer cronScheduler.Stop()

	log.Println("✓ Phase 3 services initialized:")
	log.Println("  - 🛡️ Bodyguard: Every 10 seconds (*/10 * * * * *) [FAST SL/TP]")
	log.Println("  - Virtual Broker: Every 1 minute (0 */1 * * * *)")
	log.Println("  - Review Service: Minute 5 of every hour (0 5 * * * *)")
	log.Println("  - Health Check: Every 6 hours (0 0 */6 * * *)")

	// Initialize Echo HTTP server
	e := echo.New()
	e.HideBanner = true

	// Enable CORS and logging middleware
	e.Use(middleware.CORS())
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())

	// Load HTML templates (Phase 5)
	templates, err := template.ParseGlob("web/templates/*.html")
	if err != nil {
		log.Fatalf("Failed to load templates: %v", err)
	}
	log.Println("✓ HTML templates loaded")

	// Serve static files
	e.Static("/static", "web/static")

	// Initialize HTTP handlers
	authHandler := httpdelivery.NewAuthHandler(userRepo)
	userHandler := httpdelivery.NewUserHandler(userRepo, positionRepo, tradingService)
	adminHandler := httpdelivery.NewAdminHandler(db, marketScanScheduler, signalRepo, settingsRepo)

	// Initialize web handler (Phase 5 - HTML pages)
	webHandler := httpdelivery.NewWebHandler(templates, userRepo, positionRepo, db, priceService)

	// Create auth middleware wrapper for web routes
	webAuthMiddleware := func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			// First run the JWT auth middleware
			if err := authmiddleware.AuthMiddleware(func(c echo.Context) error {
				// Fetch full user object from database using user_id from JWT
				userID, err := authmiddleware.GetUserID(c)
				if err != nil {
					return echo.NewHTTPError(http.StatusUnauthorized, "Invalid user")
				}

				user, err := userRepo.GetByID(c.Request().Context(), userID)
				if err != nil {
					return echo.NewHTTPError(http.StatusUnauthorized, "User not found")
				}

				// Set full user object in context
				c.Set("user", user)
				return next(c)
			})(c); err != nil {
				return err
			}
			return nil
		}
	}

	// Setup API routes
	httpdelivery.SetupRoutes(e, &httpdelivery.RouterConfig{
		AuthHandler:  authHandler,
		UserHandler:  userHandler,
		AdminHandler: adminHandler,
	})

	// Setup web routes (Phase 5 - HTML pages)
	httpdelivery.RegisterWebRoutes(e, webHandler, webAuthMiddleware)

	// Start HTTP server
	addr := fmt.Sprintf(":%s", cfg.Server.Port)
	log.Println("========================================")
	log.Printf("🚀 NeuroTrade Go App starting on %s", addr)
	log.Printf("📊 Environment: %s", cfg.Server.Env)
	log.Printf("💰 Default Balance: $%.2f USDT", cfg.Trading.DefaultBalance)
	log.Printf("📈 Min Confidence: %d%%", cfg.Trading.MinConfidence)
	log.Printf("🎯 Trading Mode: %s (15-min intervals)", tradingMode)
	log.Println("========================================")
	log.Println("  - POST /api/auth/login")
	log.Println("  - POST /api/auth/logout")
	log.Println("  - POST /api/auth/register")
	log.Println("  - GET  /api/user/me (protected)")
	log.Println("  - POST /api/user/mode/toggle (protected)")
	log.Println("  - GET  /api/user/positions (protected)")
	log.Println("  - POST /api/user/panic-button (protected)")
	log.Println("  - GET  /api/admin/strategies (admin)")
	log.Println("  - PUT  /api/admin/strategies/active (admin)")
	log.Println("  - GET  /api/admin/system/health (admin)")
	log.Println("  - GET  /api/admin/statistics (admin)")
	log.Println("  - POST /api/admin/market-scan/trigger (admin)")
	log.Println("========================================")

	// Run server in goroutine
	go func() {
		if err := e.Start(addr); err != nil {
			log.Printf("Server stopped: %v", err)
		}
	}()

	// Wait for interrupt signal to gracefully shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")

	// Graceful shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := e.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("✓ Server exited gracefully")
}
