package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/joho/godotenv"
	"github.com/robfig/cron/v3"

	"neurotrade/configs"
	"neurotrade/internal/adapter"
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

	// Create default user for Phase 3 (later will be per-user authentication)
	defaultUserID := ensureDefaultUser(ctx, userRepo)

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

	// Initialize HTTP router
	r := chi.NewRouter()

	// Middleware
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Timeout(60 * time.Second))

	// Routes
	r.Get("/", handleRoot)
	r.Get("/health", handleHealth(db))
	r.Post("/scan/trigger", handleTriggerScan(marketScanScheduler))
	r.Get("/signals/recent", handleGetRecentSignals(tradingService))

	// Start HTTP server
	addr := fmt.Sprintf(":%s", cfg.Server.Port)
	log.Printf("🚀 NeuroTrade Go App starting on %s", addr)
	log.Printf("📊 Environment: %s", cfg.Server.Env)
	log.Printf("💰 Default Balance: $%.2f USDT", cfg.Trading.DefaultBalance)
	log.Printf("📈 Min Confidence: %d%%", cfg.Trading.MinConfidence)
	log.Println("========================================")

	// Create HTTP server
	srv := &http.Server{
		Addr:         addr,
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Run server in goroutine
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
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

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("✓ Server exited gracefully")
}

// HTTP Handlers

func handleRoot(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{
		"message": "Welcome to NeuroTrade AI - Golang Service",
		"version": "0.1.0",
		"endpoints": {
			"health": "GET /health",
			"trigger_scan": "POST /scan/trigger",
			"recent_signals": "GET /signals/recent"
		}
	}`))
}

func handleHealth(db interface{ Ping(context.Context) error }) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Check database
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()

		dbStatus := "healthy"
		if err := db.Ping(ctx); err != nil {
			dbStatus = "unhealthy"
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(fmt.Sprintf(`{
			"status": "healthy",
			"service": "neurotrade-go-app",
			"database": "%s",
			"timestamp": "%s"
		}`, dbStatus, time.Now().Format(time.RFC3339))))
	}
}

func ensureDefaultUser(ctx context.Context, userRepo domain.UserRepository) uuid.UUID {
	// Try to get existing default user
	defaultUser, err := userRepo.GetByUsername(ctx, "default")
	if err == nil {
		log.Printf("✓ Using existing default user: %s", defaultUser.ID)
		return defaultUser.ID
	}

	// Create new default user
	log.Println("Creating default user for paper trading...")
	userID := uuid.New()
	user := &domain.User{
		ID:           userID,
		Username:     "default",
		PasswordHash: "none", // No auth in Phase 3
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
	return userID
}

func handleTriggerScan(scheduler *infra.Scheduler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		log.Println("Manual scan triggered via API")

		go func() {
			if err := scheduler.RunNow(); err != nil {
				log.Printf("ERROR: Manual scan failed: %v", err)
			}
		}()

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		w.Write([]byte(`{
			"message": "Market scan triggered successfully",
			"status": "processing"
		}`))
	}
}

func handleGetRecentSignals(tradingService *usecase.TradingService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		signals, err := tradingService.GetRecentSignals(ctx, 20)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte(fmt.Sprintf(`{"error": "%s"}`, err.Error())))
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)

		// Simple JSON response
		if len(signals) == 0 {
			w.Write([]byte(`{"signals": []}`))
			return
		}

		// Build JSON manually for simplicity
		response := `{"signals": [`
		for i, signal := range signals {
			if i > 0 {
				response += ","
			}
			response += fmt.Sprintf(`{
				"id": "%s",
				"symbol": "%s",
				"type": "%s",
				"entry_price": %.8f,
				"sl_price": %.8f,
				"tp_price": %.8f,
				"confidence": %d,
				"status": "%s",
				"created_at": "%s"
			}`,
				signal.ID,
				signal.Symbol,
				signal.Type,
				signal.EntryPrice,
				signal.SLPrice,
				signal.TPPrice,
				signal.Confidence,
				signal.Status,
				signal.CreatedAt.Format(time.RFC3339),
			)
		}
		response += `]}`

		w.Write([]byte(response))
	}
}
