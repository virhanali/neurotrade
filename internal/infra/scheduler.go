package infra

import (
	"context"
	"log"
	"time"

	"github.com/robfig/cron/v3"

	"neurotrade/internal/usecase"
)

// Scheduler manages scheduled tasks
type Scheduler struct {
	cron           *cron.Cron
	tradingService *usecase.TradingService
	balance        float64
	mode           string // "SCALPER" or "INVESTOR"
}

// NewScheduler creates a new scheduler
// mode defaults to "SCALPER" if empty
func NewScheduler(tradingService *usecase.TradingService, balance float64, mode string) *Scheduler {
	if mode == "" {
		mode = "SCALPER"
	}
	return &Scheduler{
		cron:           cron.New(cron.WithSeconds()),
		tradingService: tradingService,
		balance:        balance,
		mode:           mode,
	}
}

// Start starts the scheduler with dynamic frequency
func (s *Scheduler) Start() error {
	log.Printf("Starting scheduler... [Mode: %s]", s.mode)

	// OPTIMIZED for API cost & performance (UPDATED TO AVOID BANS):
	// Overlap (London+NY): 13:00-16:00 UTC → AGGRESSIVE (every 30s)
	// Golden Hours: 00:00-04:00, 07:00-11:00, 13:00-18:00 UTC → NORMAL (every 1 min)
	// Dead Hours: Everything else → SLOW (every 5 min)

	// Base trigger: Every 30 seconds (High frequency)
	// We handle the finer logic (1m, 5m) inside the function
	_, err := s.cron.AddFunc("*/30 * * * * *", func() {
		ctx := context.Background()
		now := time.Now().UTC()
		hour := now.Hour()
		second := now.Second()

		// === SESSION CLASSIFICATION (UTC) ===
		// Overlap (London+NY): 13:00-16:00 UTC → AGGRESSIVE (every 30s)
		// Golden Hours: 00:00-04:00, 07:00-11:00, 13:00-18:00 UTC → NORMAL (every 1 min)
		// Dead Hours: Everything else → SLOW (every 5 min)

		isOverlapHour := hour >= 13 && hour < 16
		isGoldenHour := (hour >= 0 && hour < 4) || (hour >= 7 && hour < 11) || (hour >= 13 && hour < 18)

		// DYNAMIC FREQUENCY (RELAXED TO AVOID BANS):
		if isOverlapHour {
			// Overlap hours: run EVERY 30 seconds (:00, :30)
			if second != 0 && second != 30 {
				return
			}
		} else if isGoldenHour {
			// Golden hours: run EVERY 1 minute (:00)
			if second != 0 {
				return
			}
		} else {
			// Dead hours: run EVERY 5 minutes
			// Note: This requires the cron to trigger at least once/minute.
			// Current cron triggers every 10s, so this works.
			minute := now.Minute()
			if second != 0 || minute%5 != 0 {
				return
			}
		}

		// Log with frequency indicator
		freq := "30s [AGGRESSIVE]"
		if isGoldenHour {
			freq = "1m [NORMAL]"
		} else if !isOverlapHour && !isGoldenHour {
			freq = "5m [SLOW]"
		}

		log.Printf("[CRON] Scan triggered (%s) [Mode: %s]", freq, s.mode)

		if err := s.tradingService.ProcessMarketScan(ctx, s.balance, s.mode); err != nil {
			log.Printf("ERROR: Scheduled market scan failed: %v", err)
		}
	})

	if err != nil {
		return err
	}

	// Start cron scheduler
	s.cron.Start()
	log.Println("[OK] Scheduler started successfully")
	log.Println("[OK] Dynamic frequency: 30s (Overlap) | 1m (Golden) | 5m (Dead)")
	log.Println("[OK] Optimized for API cost efficiency while maintaining responsiveness")

	return nil
}

// Stop stops the scheduler gracefully
func (s *Scheduler) Stop() {
	log.Println("Stopping scheduler...")
	s.cron.Stop()
	log.Println("[OK] Scheduler stopped")
}

// SetMode updates trading mode
func (s *Scheduler) SetMode(mode string) {
	s.mode = mode
	log.Printf("[OK] Scheduler mode updated to: %s", mode)
}

// GetMode returns current trading mode
func (s *Scheduler) GetMode() string {
	return s.mode
}
