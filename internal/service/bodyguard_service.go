package service

import (
	"context"
	"log"
	"os"
	"strconv"
	"strings"
	"time"

	"neurotrade/internal/domain"
)

// getEnvFloat gets an environment variable as float64 or returns a default value
func getEnvFloat(key string, defaultValue float64) float64 {
	if value := os.Getenv(key); value != "" {
		if floatVal, err := strconv.ParseFloat(value, 64); err == nil {
			return floatVal
		}
	}
	return defaultValue
}

// BodyguardService provides fast position monitoring (10-second interval)
// This is the "safety net" that checks SL/TP more frequently than the 1-minute Virtual Broker
type BodyguardService struct {
	positionRepo domain.PositionRepository
	userRepo     domain.UserRepository
	priceService *MarketPriceService
	signalRepo   domain.SignalRepository
	notifService NotificationService // Use same interface as VirtualBroker
	aiService    domain.AIService    // Python Bridge for WebSocket prices
}

// NewBodyguardService creates a new BodyguardService
func NewBodyguardService(
	positionRepo domain.PositionRepository,
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
			log.Printf("[WARN] Bodyguard: WebSocket price fetch failed (fallback to REST): %v", err)
		}
		prices, err = s.priceService.FetchRealTimePrices(ctx, symbols)
		if err != nil {
			log.Printf("[WARN] Bodyguard: REST price fetch failed: %v", err)
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
		shouldClose, status, closedBy := pos.CheckSLTP(currentPrice)
		if shouldClose {
			err := s.closePosition(ctx, pos, currentPrice, status, closedBy)
			if err != nil {
				log.Printf("[WARN] Bodyguard: Failed to close %s: %v", pos.Symbol, err)
				continue
			}
			closedCount++
			log.Printf("[GUARD] Bodyguard: Closed %s via %s @ $%.4f", pos.Symbol, closedBy, currentPrice)
		} else {
			// Try to apply Trailing Stop if profit is good
			s.applyTrailingStop(ctx, pos, currentPrice)
		}
	}

	if closedCount > 0 {
		log.Printf("[GUARD] Bodyguard: Closed %d position(s)", closedCount)
	}

	return nil
}

// closePosition closes a position and updates all related records
func (s *BodyguardService) closePosition(ctx context.Context, pos *domain.Position, exitPrice float64, status string, closedBy string) error {
	// 1. Fetch User to determine Mode (Real/Paper)
	user, err := s.userRepo.GetByID(ctx, pos.UserID)
	if err != nil {
		return err
	}

	// 2. REAL TRADING EXECUTION
	if user.Mode == domain.ModeReal {
		// Determine Closing Side (Opposite of Position Side)
		closeSide := "SELL"
		if pos.Side == "SHORT" { // Assuming Side is stored as "LONG" or "SHORT"
			closeSide = "BUY"
		}

		// Execute Close via Python Engine -> Binance
		// Retry logic could be added here, but bodyguard retries every 10s anyway
		res, err := s.aiService.ExecuteClose(ctx, pos.Symbol, closeSide, pos.Size)
		if err != nil {
			log.Printf("[ERR] Bodyguard: FAILED to execute REAL CLOSE for %s: %v", pos.Symbol, err)
			return err // Return error so Bodyguard will retry in next cycle
		}

		// Use ACTUAL execution price from Binance
		exitPrice = res.AvgPrice
		log.Printf("[GUARD] REAL EXECUTION SUCCESS: %s Closed @ %.4f", pos.Symbol, exitPrice)
	}

	// 3. Calculate PnL Stats (Valid for both Real & Paper for reporting)
	// Calculate Net PnL (Gross - Fees)
	grossPnL := pos.CalculateGrossPnL(exitPrice)

	// Apply fees using Binance Futures taker fee (0.04% for market orders)
	// Both entry and exit are market orders, so use taker fee
	feeRate := 0.04 / 100.0 // 0.04% = 0.0004
	fees := (pos.EntryPrice * pos.Size * feeRate) + (exitPrice * pos.Size * feeRate)
	pnl := grossPnL - fees

	// Calculate PnL percentage
	pnlPercent := pos.CalculatePnLPercent(exitPrice)

	// Determine result
	result := "WIN"
	actualStatus := domain.StatusClosedWin
	if pnl < 0 {
		result = "LOSS"
		actualStatus = domain.StatusClosedLoss
	}

	// Update position record
	now := time.Now()
	pos.Status = actualStatus
	pos.ExitPrice = &exitPrice
	pos.PnL = &pnl
	pos.PnLPercent = &pnlPercent
	pos.ClosedBy = &closedBy
	pos.ClosedAt = &now

	if err := s.positionRepo.Update(ctx, pos); err != nil {
		return err
	}

	// 4. Update Balance (ONLY FOR PAPER MODE)
	if user.Mode == domain.ModePaper {
		newBalance := user.PaperBalance + pnl
		if err := s.userRepo.UpdateBalance(ctx, user.ID, newBalance, domain.ModePaper); err != nil {
			log.Printf("[WARN] Failed to update user balance: %v", err)
		}
	}

	// 5. ML Feedback & Notifications (Common)
	var sig *domain.Signal
	if pos.SignalID != nil {
		sig, _ = s.signalRepo.GetByID(ctx, *pos.SignalID)

		// Update signal status
		if err := s.signalRepo.UpdateReviewStatus(ctx, *pos.SignalID, result, &pnlPercent); err != nil {
			log.Printf("[WARN] Failed to update signal status: %v", err)
		}
	}

	// Send ML Feedback to Python Engine (async)
	go func() {
		feedbackCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		feedback := &domain.FeedbackData{
			Symbol:  pos.Symbol,
			Outcome: result,
			PnL:     pnlPercent,
		}

		if sig != nil && sig.ScreenerMetrics != nil {
			feedback.Metrics = sig.ScreenerMetrics
		}

		if err := s.aiService.SendFeedback(feedbackCtx, feedback); err != nil {
			log.Printf("[WARN] Failed to send ML feedback: %v", err)
		}
	}()

	// Send notification
	if s.notifService != nil && sig != nil {
		sig.ReviewResult = &result
		if err := s.notifService.SendReview(*sig, &pnl); err != nil {
			log.Printf("[WARN] Failed to send notification: %v", err)
		}
	}

	return nil
}

// GetBulkPrices fetches all prices in a single API call (exported for potential reuse)
func (s *BodyguardService) GetBulkPrices(ctx context.Context, symbols []string) (map[string]float64, error) {
	return s.priceService.FetchRealTimePrices(ctx, symbols)
}

// applyTrailingStop updates SL dynamically to lock in profits
func (s *BodyguardService) applyTrailingStop(ctx context.Context, pos *domain.Position, currentPrice float64) {
	// 1. Activation Check: Must be in Profit > configured % (default 1.0%)
	activationThreshold := getEnvFloat("TRAILING_ACTIVATE_PCT", 1.0)
	pnlPct := pos.CalculatePnLPercent(currentPrice)

	if pnlPct < activationThreshold {
		return
	}

	// 2. Trailing Distance: configured % from Current Price (default 0.5%)
	trailingDistancePct := getEnvFloat("TRAILING_DISTANCE_PCT", 0.5)

	var newSL float64
	updated := false

	if pos.IsLong() {
		// LONG: New SL = Price * (1 - 0.5%)
		// Move SL UP
		trailPrice := currentPrice * (1.0 - (trailingDistancePct / 100.0))
		if trailPrice > pos.SLPrice {
			newSL = trailPrice
			updated = true
		}
	} else {
		// SHORT: New SL = Price * (1 + 0.5%)
		// Move SL DOWN
		trailPrice := currentPrice * (1.0 + (trailingDistancePct / 100.0))
		// For SHORT, SL is above price. We want to lower it.
		if trailPrice < pos.SLPrice {
			newSL = trailPrice
			updated = true
		}
	}

	if updated {
		pos.SLPrice = newSL
		// Update SL in DB
		if err := s.positionRepo.Update(ctx, pos); err != nil {
			log.Printf("[WARN] Failed to update Trailing Stop for %s: %v", pos.Symbol, err)
		} else {
			log.Printf("[TRAIL] Trailing Stop Updated for %s: New SL %.4f (Price %.4f, PnL %.2f%%)",
				pos.Symbol, pos.SLPrice, currentPrice, pnlPct)
		}
	}
}
