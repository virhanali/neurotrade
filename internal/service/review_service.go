package service

import (
	"context"
	"fmt"
	"log"
	"os"
	"strconv"

	"neurotrade/internal/domain"
)

// getReviewThreshold gets the WIN_LOSS_THRESHOLD_PCT from env or returns default
func getReviewThreshold() float64 {
	if value := os.Getenv("WIN_LOSS_THRESHOLD_PCT"); value != "" {
		if floatVal, err := strconv.ParseFloat(value, 64); err == nil {
			return floatVal
		}
	}
	return 0.5 // default 0.5%
}

// Review thresholds (loaded from environment)
var (
	ReviewWinThresholdPercent  = getReviewThreshold()  // e.g., 0.5% profit = WIN
	ReviewLossThresholdPercent = -getReviewThreshold() // e.g., -0.5% loss = LOSS
)

// NotificationService defines the interface for sending notifications
type NotificationService interface {
	SendSignal(signal domain.Signal) error
	SendReview(signal domain.Signal, pnl *float64) error
}

// ReviewService audits past signals and marks them as WIN/LOSS/FLOATING
type ReviewService struct {
	signalRepo          domain.SignalRepository
	priceService        *MarketPriceService
	notificationService NotificationService
}

// NewReviewService creates a new ReviewService
func NewReviewService(
	signalRepo domain.SignalRepository,
	priceService *MarketPriceService,
	notificationService NotificationService,
) *ReviewService {
	return &ReviewService{
		signalRepo:          signalRepo,
		priceService:        priceService,
		notificationService: notificationService,
	}
}

// ReviewPastSignals reviews signals created more than specified minutes ago
func (s *ReviewService) ReviewPastSignals(ctx context.Context, olderThanMinutes int) error {
	log.Printf("[INFO] Review Service: Reviewing signals older than %d minutes...", olderThanMinutes)

	// Get pending signals older than threshold
	signals, err := s.signalRepo.GetPendingSignals(ctx, olderThanMinutes)
	if err != nil {
		return fmt.Errorf("failed to get pending signals: %w", err)
	}

	if len(signals) == 0 {
		log.Println("[OK] No pending signals to review")
		return nil
	}

	log.Printf("Found %d signal(s) to review", len(signals))

	// Extract unique symbols
	symbolMap := make(map[string]bool)
	for _, signal := range signals {
		symbolMap[signal.Symbol] = true
	}

	symbols := make([]string, 0, len(symbolMap))
	for symbol := range symbolMap {
		symbols = append(symbols, symbol)
	}

	// Fetch current prices
	prices, err := s.priceService.FetchRealTimePrices(ctx, symbols)
	if err != nil {
		return fmt.Errorf("failed to fetch real-time prices: %w", err)
	}

	// Review each signal
	for _, signal := range signals {
		currentPrice, ok := prices[signal.Symbol]
		if !ok {
			log.Printf("WARNING: Price not found for %s, skipping", signal.Symbol)
			continue
		}

		// Calculate floating PnL percentage
		floatingPnLPercent := s.calculateFloatingPnL(signal, currentPrice)

		// Determine review result
		result, pnl := s.determineReviewResult(signal, currentPrice, floatingPnLPercent)

		// Update signal review status
		if err := s.signalRepo.UpdateReviewStatus(ctx, signal.ID, result, &pnl); err != nil {
			log.Printf("ERROR: Failed to update review status for signal %s: %v", signal.ID, err)
			continue
		}

		log.Printf("[OK] Signal Reviewed: %s %s | Entry=%.2f Current=%.2f | PnL=%.2f%% | Result=%s",
			signal.Symbol, signal.Type, signal.EntryPrice, currentPrice, floatingPnLPercent, result)

		// Send Telegram notification for WIN/LOSS (not for FLOATING)
		if s.notificationService != nil && (result == "WIN" || result == "LOSS") {
			signal.ReviewResult = &result
			if err := s.notificationService.SendReview(*signal, nil); err != nil {
				log.Printf("WARNING: Failed to send Telegram review notification: %v", err)
			}
		}
	}

	return nil
}

// calculateFloatingPnL calculates the floating PnL percentage
func (s *ReviewService) calculateFloatingPnL(signal *domain.Signal, currentPrice float64) float64 {
	var pnlPercent float64

	if signal.Type == "LONG" {
		// Long: profit when price goes up
		pnlPercent = ((currentPrice - signal.EntryPrice) / signal.EntryPrice) * 100
	} else if signal.Type == "SHORT" {
		// Short: profit when price goes down
		pnlPercent = ((signal.EntryPrice - currentPrice) / signal.EntryPrice) * 100
	}

	return pnlPercent
}

// determineReviewResult determines if signal is WIN/LOSS/FLOATING
func (s *ReviewService) determineReviewResult(signal *domain.Signal, currentPrice, pnlPercent float64) (string, float64) {
	// Check if TP or SL was hit first
	if signal.Type == "LONG" {
		if currentPrice >= signal.TPPrice {
			return "WIN", pnlPercent
		}
		if currentPrice <= signal.SLPrice {
			return "LOSS", pnlPercent
		}
	} else if signal.Type == "SHORT" {
		if currentPrice <= signal.TPPrice {
			return "WIN", pnlPercent
		}
		if currentPrice >= signal.SLPrice {
			return "LOSS", pnlPercent
		}
	}

	// If TP/SL not hit, check floating PnL thresholds
	if pnlPercent >= ReviewWinThresholdPercent {
		return "FLOATING_WIN", pnlPercent
	}
	if pnlPercent <= ReviewLossThresholdPercent {
		return "FLOATING_LOSS", pnlPercent
	}

	return "FLOATING", pnlPercent
}
