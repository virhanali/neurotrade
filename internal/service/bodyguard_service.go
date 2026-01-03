package service

import (
	"context"
	"log"
	"strings"
	"time"

	"neurotrade/internal/domain"
)

// BodyguardService provides fast position monitoring (10-second interval)
// This is the "safety net" that checks SL/TP more frequently than the 1-minute Virtual Broker
type BodyguardService struct {
	positionRepo domain.PaperPositionRepository
	userRepo     domain.UserRepository
	priceService *MarketPriceService
	signalRepo   domain.SignalRepository
	notifService NotificationService // Use same interface as VirtualBroker
	aiService    domain.AIService    // Python Bridge for WebSocket prices
}

// NewBodyguardService creates a new BodyguardService
func NewBodyguardService(
	positionRepo domain.PaperPositionRepository,
	userRepo domain.UserRepository,
	priceService *MarketPriceService,
	signalRepo domain.SignalRepository,
	notifService NotificationService,
	aiService domain.AIService,
) *BodyguardService {
	return &BodyguardService{
		positionRepo: positionRepo,
		userRepo:     userRepo,
		priceService: priceService,
		signalRepo:   signalRepo,
		notifService: notifService,
		aiService:    aiService,
	}
}

// CheckPositionsFast performs a fast bulk price check against all open positions
// This is optimized for 10-second intervals with minimal API weight
func (s *BodyguardService) CheckPositionsFast(ctx context.Context) error {
	// Get all open positions
	positions, err := s.positionRepo.GetOpenPositions(ctx)
	if err != nil {
		return err
	}

	if len(positions) == 0 {
		return nil // No positions to check
	}

	// Collect unique symbols for bulk fetch
	symbolSet := make(map[string]bool)
	for _, pos := range positions {
		symbolSet[pos.Symbol] = true
	}

	symbols := make([]string, 0, len(symbolSet))
	for symbol := range symbolSet {
		symbols = append(symbols, symbol)
	}

	// 1. Try WebSocket prices first (Fastest)
	var prices map[string]float64
	prices, err = s.aiService.GetWebSocketPrices(ctx, symbols)

	// 2. Fallback to REST API if WebSocket fails
	if err != nil || len(prices) == 0 {
		if err != nil {
			log.Printf("⚠️ Bodyguard: WebSocket price fetch failed (fallback to REST): %v", err)
		}
		prices, err = s.priceService.FetchRealTimePrices(ctx, symbols)
		if err != nil {
			log.Printf("⚠️ Bodyguard: REST price fetch failed: %v", err)
			return nil
		}
	}

	// Check each position against fetched prices
	closedCount := 0
	for _, pos := range positions {
		currentPrice, ok := prices[pos.Symbol]
		if !ok {
			// Try normalized symbol
			normalizedSymbol := strings.ReplaceAll(pos.Symbol, "/", "")
			currentPrice, ok = prices[normalizedSymbol]
			if !ok {
				continue // Skip if price not found
			}
		}

		// Check SL/TP
		shouldClose, status := pos.CheckSLTP(currentPrice)
		if shouldClose {
			err := s.closePosition(ctx, pos, currentPrice, status)
			if err != nil {
				log.Printf("⚠️ Bodyguard: Failed to close %s: %v", pos.Symbol, err)
				continue
			}
			closedCount++
			log.Printf("🛡️ Bodyguard: Closed %s via %s @ $%.4f", pos.Symbol, status, currentPrice)
		}
	}

	if closedCount > 0 {
		log.Printf("🛡️ Bodyguard: Closed %d position(s)", closedCount)
	}

	return nil
}

// closePosition closes a position and updates all related records
func (s *BodyguardService) closePosition(ctx context.Context, pos *domain.PaperPosition, exitPrice float64, status string) error {
	// Calculate Net PnL (Gross - Fees)
	grossPnL := pos.CalculateGrossPnL(exitPrice)

	// Apply fees (0.05% maker + 0.05% taker = 0.1% total)
	feeRate := TradingFeePercent / 100.0
	fees := (pos.EntryPrice * pos.Size * feeRate) + (exitPrice * pos.Size * feeRate)
	pnl := grossPnL - fees

	// Update position
	now := time.Now()
	pos.Status = status
	pos.ExitPrice = &exitPrice
	pos.PnL = &pnl
	pos.ClosedAt = &now

	if err := s.positionRepo.Update(ctx, pos); err != nil {
		return err
	}

	// Update user balance
	user, err := s.userRepo.GetByID(ctx, pos.UserID)
	if err == nil {
		newBalance := user.PaperBalance + pnl
		if err := s.userRepo.UpdateBalance(ctx, user.ID, newBalance, domain.ModePaper); err != nil {
			log.Printf("⚠️ Failed to update user balance: %v", err)
		}
	}

	// Update signal status if linked
	if pos.SignalID != nil {
		result := "WIN"
		if pnl < 0 {
			result = "LOSS"
		}

		// Calculate PnL percentage
		pnlPercent := pos.CalculatePnLPercent(exitPrice)

		if err := s.signalRepo.UpdateReviewStatus(ctx, *pos.SignalID, result, &pnlPercent); err != nil {
			log.Printf("⚠️ Failed to update signal status: %v", err)
		}
	}

	// Send notification
	if s.notifService != nil && pos.SignalID != nil {
		if sig, err := s.signalRepo.GetByID(ctx, *pos.SignalID); err == nil {
			result := "WIN"
			if pnl < 0 {
				result = "LOSS"
			}
			sig.ReviewResult = &result
			if err := s.notifService.SendReview(*sig, &pnl); err != nil {
				log.Printf("⚠️ Failed to send notification: %v", err)
			}
		}
	}

	return nil
}

// GetBulkPrices fetches all prices in a single API call (exported for potential reuse)
func (s *BodyguardService) GetBulkPrices(ctx context.Context, symbols []string) (map[string]float64, error) {
	return s.priceService.FetchRealTimePrices(ctx, symbols)
}
