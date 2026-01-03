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

// Start starts the scheduler
func (s *Scheduler) Start() error {
	log.Printf("Starting scheduler... [Mode: %s]", s.mode)

	// Schedule market scan every 15 seconds for SCALPER mode (*/15 * * * * *)
	// ULTRA AGGRESSIVE MODE: Captures pumps immediately.
	// Safe because overlap is prevented by Mutex in trading_service.
	_, err := s.cron.AddFunc("*/15 * * * * *", func() {
		ctx := context.Background()
		log.Printf("[CRON] Cron Triggered: Starting scheduled market scan [Mode: %s]...", s.mode)

		if err := s.tradingService.ProcessMarketScan(ctx, s.balance, s.mode); err != nil {
			log.Printf("ERROR: Scheduled market scan failed: %v", err)
		}
	})

	if err != nil {
		return err
	}

	// Start the cron scheduler
	s.cron.Start()
	log.Println("✓ Scheduler started successfully")
	log.Printf("✓ Market scan scheduled every 15 seconds (*/15 * * * * *) [Mode: %s]", s.mode)

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
	log.Printf("[SIGNAL] Manual Trigger: Starting immediate market scan [Mode: %s]...", s.mode)
	return s.tradingService.ProcessMarketScan(ctx, s.balance, s.mode)
}

// SetMode updates the trading mode
func (s *Scheduler) SetMode(mode string) {
	s.mode = mode
	log.Printf("✓ Scheduler mode updated to: %s", mode)
}

// GetMode returns the current trading mode
func (s *Scheduler) GetMode() string {
	return s.mode
}
