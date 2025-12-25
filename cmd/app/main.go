package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/joho/godotenv"
	"github.com/labstack/echo/v4"
	"github.com/robfig/cron/v3"
	"golang.org/x/crypto/bcrypt"

	"neurotrade/configs"
	"neurotrade/internal/adapter"
	httpdelivery "neurotrade/internal/delivery/http"
	"neurotrade/internal/domain"
	"neurotrade/internal/infra"
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

	// Initialize database
	db, err := infra.NewDatabase(ctx, cfg.Database.URL)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	// Initialize repositories
	signalRepo := repository.NewSignalRepository(db)
	userRepo := repository.NewUserRepository(db)
	positionRepo := repository.NewPaperPositionRepository(db)

	// Create default user for Phase 3-4 (later will be per-user authentication)
	defaultUserID := ensureDefaultUserWithPassword(ctx, userRepo)

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
	virtualBroker := service.NewVirtualBrokerService(positionRepo, userRepo, priceService)
	reviewService := service.NewReviewService(signalRepo, priceService)

	// Initialize trading service
	tradingService := usecase.NewTradingService(
		aiService,
		signalRepo,
		positionRepo,
		userRepo,
		cfg.Trading.MinConfidence,
		defaultUserID,
	)

	// Initialize market scan scheduler
	marketScanScheduler := infra.NewScheduler(tradingService, cfg.Trading.DefaultBalance)
	if err := marketScanScheduler.Start(); err != nil {
		log.Fatalf("Failed to start market scan scheduler: %v", err)
	}
	defer marketScanScheduler.Stop()

	// Initialize Phase 3 cron jobs
	cronScheduler := cron.New()

	// Virtual Broker: Check positions every 1 minute
	_, err = cronScheduler.AddFunc("*/1 * * * *", func() {
		ctx := context.Background()
		if err := virtualBroker.CheckPositions(ctx); err != nil {
			log.Printf("ERROR: Virtual broker check failed: %v", err)
		}
	})
	if err != nil {
		log.Fatalf("Failed to add virtual broker cron job: %v", err)
	}

	// Review Service: Review signals at minute 5 of every hour
	_, err = cronScheduler.AddFunc("5 * * * *", func() {
		ctx := context.Background()
		if err := reviewService.ReviewPastSignals(ctx, 60); err != nil {
			log.Printf("ERROR: Review service failed: %v", err)
		}
	})
	if err != nil {
		log.Fatalf("Failed to add review service cron job: %v", err)
	}

	// Start Phase 3 cron scheduler
	cronScheduler.Start()
	defer cronScheduler.Stop()

	log.Println("✓ Phase 3 services initialized:")
	log.Println("  - Virtual Broker: Every 1 minute (*/1 * * * *)")
	log.Println("  - Review Service: Minute 5 of every hour (5 * * * *)")

	// Initialize Echo HTTP server
	e := echo.New()
	e.HideBanner = true

	// Initialize HTTP handlers
	authHandler := httpdelivery.NewAuthHandler(userRepo)
	userHandler := httpdelivery.NewUserHandler(userRepo, positionRepo, tradingService)
	adminHandler := httpdelivery.NewAdminHandler(db)

	// Setup routes
	httpdelivery.SetupRoutes(e, &httpdelivery.RouterConfig{
		AuthHandler:  authHandler,
		UserHandler:  userHandler,
		AdminHandler: adminHandler,
	})

	// Start HTTP server
	addr := fmt.Sprintf(":%s", cfg.Server.Port)
	log.Println("========================================")
	log.Printf("🚀 NeuroTrade Go App starting on %s", addr)
	log.Printf("📊 Environment: %s", cfg.Server.Env)
	log.Printf("💰 Default Balance: $%.2f USDT", cfg.Trading.DefaultBalance)
	log.Printf("📈 Min Confidence: %d%%", cfg.Trading.MinConfidence)
	log.Println("========================================")
	log.Println("✅ Phase 4 API Endpoints:")
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

func ensureDefaultUserWithPassword(ctx context.Context, userRepo domain.UserRepository) uuid.UUID {
	// Try to get existing default user
	defaultUser, err := userRepo.GetByUsername(ctx, "default")
	if err == nil {
		log.Printf("✓ Using existing default user: %s", defaultUser.ID)
		return defaultUser.ID
	}

	// Create new default user with hashed password
	log.Println("Creating default user for paper trading...")
	userID := uuid.New()

	// Hash default password "password123"
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte("password123"), bcrypt.DefaultCost)
	if err != nil {
		log.Fatalf("Failed to hash password: %v", err)
	}

	user := &domain.User{
		ID:           userID,
		Username:     "default",
		PasswordHash: string(hashedPassword),
		Role:         domain.RoleUser,
		PaperBalance: 1000.0, // Start with $1000 paper balance
		Mode:         domain.ModePaper,
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	if err := userRepo.Create(ctx, user); err != nil {
		log.Printf("WARNING: Failed to create default user: %v", err)
		log.Println("Paper trading will not work without a default user")
		return uuid.Nil
	}

	log.Printf("✓ Created default user with $%.2f paper balance", user.PaperBalance)
	log.Println("  Username: default")
	log.Println("  Password: password123")
	return userID
}
