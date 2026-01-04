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
			log.Println("[OK] Database connected successfully")
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

	// === SELF-HEALING: Fix Signal Status ===
	// Ensure signals linked to positions are marked as EXECUTED
	_, err = db.Exec(ctx, `
		UPDATE signals 
		SET status = 'EXECUTED' 
		WHERE id IN (
			SELECT signal_id 
			FROM paper_positions 
			WHERE signal_id IS NOT NULL
		) 
		AND status = 'PENDING'
	`)
	if err != nil {
		log.Printf("[WARN] Self-healing failed: %v", err)
	} else {
		log.Println("[OK] Self-healing: Synced signal statuses")
	}

	// Initialize repositories
	signalRepo := repository.NewSignalRepository(db)
	userRepo := repository.NewUserRepository(db)
	positionRepo := repository.NewPaperPositionRepository(db)
	// settingsRepo removed as part of Scalper-Only lock

	// Initialize Telegram notification service (Phase 5)
	telegramBotToken := os.Getenv("TELEGRAM_BOT_TOKEN")
	telegramChatID := os.Getenv("TELEGRAM_CHAT_ID")

	notificationService := telegram.NewNotificationService(telegramBotToken, telegramChatID)

	// Initialize Telegram Bot Controller for remote commands
	var botController *telegram.BotController
	if telegramBotToken != "" && telegramChatID != "" {
		log.Println("[OK] Telegram notifications enabled")

		// Create bot controller
		botController = telegram.NewBotController(notificationService)

		// Register commands (handlers will be set after services are initialized)
		log.Println("[OK] Telegram Bot Controller initialized")
	} else {
		log.Println("[WARN]  Telegram notifications disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable)")
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
			log.Println("[OK] Python Engine is healthy")
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

	// Load trading mode (Locked to SCALPER)
	tradingMode := "SCALPER"
	log.Printf("[OK] Trading mode locked to: %s", tradingMode)

	// Initialize market scan scheduler
	marketScanScheduler := infra.NewScheduler(tradingService, cfg.Trading.DefaultBalance, tradingMode)
	if err := marketScanScheduler.Start(); err != nil {
		log.Fatalf("Failed to start market scan scheduler: %v", err)
	}
	defer marketScanScheduler.Stop()

	// Register Telegram Bot commands (if enabled)
	if botController != nil {
		// /status command
		botController.RegisterCommand("/status", func() string {
			return fmt.Sprintf("✅ *Bot Status*\n\n"+
				"Mode: `%s`\n"+
				"Scheduler: `Running`\n"+
				"Time: `%s`",
				tradingMode,
				time.Now().Format("2006-01-02 15:04:05"))
		})

		// /balance command
		botController.RegisterCommand("/balance", func() string {
			users, _ := userRepo.GetAll(ctx)
			if len(users) == 0 {
				return "No users found"
			}
			user := users[0]
			return fmt.Sprintf("💰 *Balance*\n\n"+
				"Paper: `$%.2f`\n"+
				"Mode: `%s`",
				user.PaperBalance,
				user.Mode)
		})

		// /stats command
		botController.RegisterCommand("/stats", func() string {
			// Get all users to calculate total balance
			users, _ := userRepo.GetAll(ctx)
			totalBalance := 0.0
			for _, u := range users {
				totalBalance += u.PaperBalance
			}

			// Get open positions
			openPositions, _ := positionRepo.GetOpenPositions(ctx)

			return fmt.Sprintf("📊 *Trading Stats*\n\n"+
				"Total Balance: `$%.2f`\n"+
				"Open Positions: `%d`\n"+
				"Mode: `%s`",
				totalBalance, len(openPositions), tradingMode)
		})

		// /positions command
		botController.RegisterCommand("/positions", func() string {
			positions, _ := positionRepo.GetOpenPositions(ctx)
			if len(positions) == 0 {
				return "No open positions"
			}
			msg := "📈 *Open Positions*\n\n"
			for _, p := range positions {
				msg += fmt.Sprintf("• %s %s @ $%.4f\n", p.Symbol, p.Side, p.EntryPrice)
			}
			return msg
		})

		// Start polling for commands
		botController.StartPolling()
		defer botController.StopPolling()
		log.Println("[OK] Telegram Bot polling started")
	}

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
				log.Printf("[WARN] HEALTH CHECK FAILED: Python Engine is not available: %v", err)
			} else {
				log.Println("[OK] Health check passed: Python Engine is healthy")
			}
		}
	})
	if err != nil {
		log.Fatalf("Failed to add health check cron job: %v", err)
	}

	// Start Phase 3 cron scheduler
	cronScheduler.Start()
	defer cronScheduler.Stop()

	log.Println("[OK] Phase 3 services initialized:")
	log.Println("  - [GUARD] Bodyguard: Every 10 seconds (*/10 * * * * *) [FAST SL/TP]")
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
	log.Println("[OK] HTML templates loaded")

	// Serve static files
	e.Static("/static", "web/static")

	// Initialize HTTP handlers
	authHandler := httpdelivery.NewAuthHandler(userRepo)
	userHandler := httpdelivery.NewUserHandler(userRepo, positionRepo, tradingService)
	adminHandler := httpdelivery.NewAdminHandler(db, marketScanScheduler, signalRepo, positionRepo, templates)

	// Initialize web handler (Phase 5 - HTML pages)
	webHandler := httpdelivery.NewWebHandler(templates, userRepo, positionRepo, db, priceService)

	// Create auth middleware wrapper for web routes
	webAuthMiddleware := func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {

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
				return c.Redirect(http.StatusFound, "/login?error=Session+expired")
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
	log.Printf("[SIGNAL] NeuroTrade v2.5 (Aggressive Scalper) starting on %s", addr)
	log.Printf("[INFO] Environment: %s", cfg.Server.Env)
	log.Printf("💰 Default Balance: $%.2f USDT", cfg.Trading.DefaultBalance)
	log.Printf("📈 Min Confidence: %d%%", cfg.Trading.MinConfidence)
	if tradingMode == "SCALPER" {
		log.Printf("[TARGET] Trading Mode: %s (2-min intervals)", tradingMode)
	} else {
		log.Printf("[TARGET] Trading Mode: %s (60-min intervals)", tradingMode)
	}
	log.Println("========================================")
	log.Println("AVAILABLE ROUTES:")
	log.Println("  [Auth]")
	log.Println("  - POST /api/auth/register")
	log.Println("  - POST /api/auth/login")
	log.Println("  - POST /api/auth/logout")

	log.Println("  [User]")
	log.Println("  - GET  /api/user/me")
	log.Println("  - GET  /api/user/positions")
	log.Println("  - POST /api/user/mode/toggle")
	log.Println("  - POST /api/user/panic-button")

	log.Println("  [Admin/System]")
	log.Println("  - POST /api/admin/market-scan/trigger")
	log.Println("  - GET  /api/admin/system/health")
	log.Println("  - GET  /api/admin/statistics")
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

	log.Println("[OK] Server exited gracefully")
}
