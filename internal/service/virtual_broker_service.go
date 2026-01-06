package service

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"neurotrade/internal/domain"
)

const (
	// Binance spot trading fee (Maker/Taker)
	TradingFeePercent = 0.05 // 0.05% = 0.0005 in decimal
)

// VirtualBrokerService simulates trade execution with realistic fees
type VirtualBrokerService struct {
	positionRepo        domain.PositionRepository
	userRepo            domain.UserRepository
	priceService        *MarketPriceService
	signalRepo          domain.SignalRepository
	notificationService NotificationService // Reuse interface from trading/review service or define new one
}

// NewVirtualBrokerService creates a new VirtualBrokerService
func NewVirtualBrokerService(
	positionRepo domain.PositionRepository,
	userRepo domain.UserRepository,
	priceService *MarketPriceService,
	signalRepo domain.SignalRepository,
	notificationService NotificationService,
) *VirtualBrokerService {
	return &VirtualBrokerService{
		positionRepo:        positionRepo,
		userRepo:            userRepo,
		priceService:        priceService,
		signalRepo:          signalRepo,
		notificationService: notificationService,
	}
}

// CheckPositions checks all open positions and closes them if TP/SL is hit
func (s *VirtualBrokerService) CheckPositions(ctx context.Context) error {
	// Get all open positions
	positions, err := s.positionRepo.GetOpenPositions(ctx)
	if err != nil {
		return fmt.Errorf("failed to get open positions: %w", err)
	}

	if len(positions) == 0 {
		return nil
	}

	log.Printf("Found %d open position(s)", len(positions))

	// Extract unique symbols
	symbolMap := make(map[string]bool)
	for _, pos := range positions {
		symbolMap[pos.Symbol] = true
	}

	symbols := make([]string, 0, len(symbolMap))
	for symbol := range symbolMap {
		symbols = append(symbols, symbol)
	}

	// Fetch current prices
	prices, err := s.priceService.FetchRealTimePrices(ctx, symbols)
	if err != nil {
		// If it's just missing prices for some symbols, we warn but continue with the ones we found
		if strings.Contains(err.Error(), "missing prices") {
			log.Printf("[WARN]  Partial Price Fetch: %v", err)
		} else {
			return fmt.Errorf("failed to fetch real-time prices: %w", err)
		}
	}

	// Check each position
	for _, position := range positions {
		currentPrice, ok := prices[position.Symbol]
		if !ok {
			log.Printf("WARNING: Price not found for %s, skipping", position.Symbol)
			continue
		}

		// Check if TP or SL is hit
		shouldClose, status, closedBy := position.CheckSLTP(currentPrice)
		if !shouldClose {
			log.Printf("Position %s: Current=%.2f, Entry=%.2f, SL=%.2f, TP=%.2f (Still OPEN)",
				position.Symbol, currentPrice, position.EntryPrice, position.SLPrice, position.TPPrice)
			continue
		}

		// Calculate PnL with fees
		netPnL := s.calculateNetPnL(position, currentPrice)
		pnlPercent := position.CalculatePnLPercent(currentPrice)

		// Close position
		now := time.Now()
		position.ExitPrice = &currentPrice
		position.PnL = &netPnL
		position.PnLPercent = &pnlPercent
		position.ClosedBy = &closedBy
		position.Status = status
		position.ClosedAt = &now

		if err := s.positionRepo.Update(ctx, position); err != nil {
			log.Printf("ERROR: Failed to update position %s: %v", position.ID, err)
			continue
		}

		// Update user balance
		user, err := s.userRepo.GetByID(ctx, position.UserID)
		if err != nil {
			log.Printf("ERROR: Failed to get user %s: %v", position.UserID, err)
			continue
		}

		newBalance := user.PaperBalance + netPnL
		if err := s.userRepo.UpdateBalance(ctx, user.ID, newBalance, domain.ModePaper); err != nil {
			log.Printf("ERROR: Failed to update user balance: %v", err)
			continue
		}

		// --- NOTIFICATION & SIGNAL UPDATE LOGIC ---
		// Determine result string for Signal Review (based on actual PnL, not trigger)
		reviewResult := "WIN"
		if netPnL < 0 {
			reviewResult = "LOSS"
			position.Status = domain.StatusClosedLoss
		} else {
			position.Status = domain.StatusClosedWin
		}

		// pnlPercent already calculated above - no need to recalculate

		// Update Signal in DB if attached
		if position.SignalID != nil {
			// Update signal review status immediately to stop ReviewService from picking it up
			if err := s.signalRepo.UpdateReviewStatus(ctx, *position.SignalID, reviewResult, &pnlPercent); err != nil {
				log.Printf("WARNING: Failed to update signal review status: %v", err)
			}

			// Send Telegram Notification
			if s.notificationService != nil {
				// Fetch signal details for notification
				if sig, err := s.signalRepo.GetByID(ctx, *position.SignalID); err == nil {
					sig.ReviewResult = &reviewResult
					// Pass netPnL (dollar amount) for user notification, NOT percentage
					if err := s.notificationService.SendReview(*sig, &netPnL); err != nil {
						log.Printf("WARNING: Failed to send auto-close notification: %v", err)
					}
				}
			}
		}
		// ------------------------------------------

		log.Printf("[OK] Position CLOSED: %s %s | Entry=%.2f Exit=%.2f | PnL=%.2f USDT | Status=%s",
			position.Symbol, position.Side, position.EntryPrice, currentPrice, netPnL, status)
		log.Printf("   User balance updated: %.2f → %.2f USDT", user.PaperBalance, newBalance)
	}

	return nil
}

// calculateNetPnL calculates net PnL after fees
// Formula:
// - GrossPnL = (ExitPrice - EntryPrice) * Size * (1 if Long, -1 if Short)
// - EntryFee = Size * EntryPrice * 0.0005
// - ExitFee = Size * ExitPrice * 0.0005
// - NetPnL = GrossPnL - EntryFee - ExitFee
func (s *VirtualBrokerService) calculateNetPnL(position *domain.Position, exitPrice float64) float64 {
	// Calculate gross PnL
	grossPnL := position.CalculateGrossPnL(exitPrice)

	// Calculate fees (0.05% on both entry and exit)
	feeRate := TradingFeePercent / 100.0 // Convert 0.05% to 0.0005
	entryFee := position.Size * position.EntryPrice * feeRate
	exitFee := position.Size * exitPrice * feeRate
	totalFees := entryFee + exitFee

	// Net PnL = Gross PnL - Fees
	netPnL := grossPnL - totalFees

	log.Printf("   PnL Calculation for %s:", position.Symbol)
	log.Printf("   - Gross PnL: %.4f USDT", grossPnL)
	log.Printf("   - Entry Fee (0.05%%): %.4f USDT", entryFee)
	log.Printf("   - Exit Fee (0.05%%): %.4f USDT", exitFee)
	log.Printf("   - Total Fees: %.4f USDT", totalFees)
	log.Printf("   - Net PnL: %.4f USDT", netPnL)

	return netPnL
}
