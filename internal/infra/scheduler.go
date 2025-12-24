package infra

import (
	"context"
	"log"

	"github.com/robfig/cron/v3"

	"neurotrade/internal/usecase"
)

// Scheduler manages scheduled tasks
type Scheduler struct {
	cron           *cron.Cron
	tradingService *usecase.TradingService
	balance        float64
}

// NewScheduler creates a new scheduler
func NewScheduler(tradingService *usecase.TradingService, balance float64) *Scheduler {
	return &Scheduler{
		cron:           cron.New(),
		tradingService: tradingService,
		balance:        balance,
	}
}

// Start starts the scheduler
func (s *Scheduler) Start() error {
	log.Println("Starting scheduler...")

	// Schedule market scan at minute 59 of every hour (59 * * * *)
	_, err := s.cron.AddFunc("59 * * * *", func() {
		ctx := context.Background()
		log.Println("⏰ Cron Triggered: Starting scheduled market scan...")

		if err := s.tradingService.ProcessMarketScan(ctx, s.balance); err != nil {
			log.Printf("ERROR: Scheduled market scan failed: %v", err)
		}
	})

	if err != nil {
		return err
	}

	// Start the cron scheduler
	s.cron.Start()
	log.Println("✓ Scheduler started successfully")
	log.Println("✓ Market scan scheduled at minute 59 of every hour (59 * * * *)")

	return nil
}

// Stop stops the scheduler gracefully
func (s *Scheduler) Stop() {
	log.Println("Stopping scheduler...")
	s.cron.Stop()
	log.Println("✓ Scheduler stopped")
}

// RunNow triggers an immediate market scan (useful for testing)
func (s *Scheduler) RunNow() error {
	ctx := context.Background()
	log.Println("🚀 Manual Trigger: Starting immediate market scan...")
	return s.tradingService.ProcessMarketScan(ctx, s.balance)
}
