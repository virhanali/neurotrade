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
	// Binance Futures trading fee (Maker/Taker)
	// Market orders use taker fee (0.04%)
	// Limit orders use maker fee (0.02%)
	TradingFeeTakerPercent = 0.04 // 0.04% = 0.0004 in decimal
	TradingFeeMakerPercent = 0.02 // 0.02% = 0.0002 in decimal
)

// VirtualBrokerService simulates trade execution with realistic fees
type VirtualBrokerService struct {
	positionRepo        domain.PositionRepository
	userRepo            domain.UserRepository
	priceService        *MarketPriceService
	signalRepo          domain.SignalRepository
	notificationService NotificationService
	aiService           domain.AIService // Added for Real Trading Execution
}

// NewVirtualBrokerService creates a new VirtualBrokerService
func NewVirtualBrokerService(
	positionRepo domain.PositionRepository,
	userRepo domain.UserRepository,
	priceService *MarketPriceService,
	signalRepo domain.SignalRepository,
	notificationService NotificationService,
	aiService domain.AIService, // Injected dependency
) *VirtualBrokerService {
	return &VirtualBrokerService{
		positionRepo:        positionRepo,
		userRepo:            userRepo,
		priceService:        priceService,
		signalRepo:          signalRepo,
		notificationService: notificationService,
		aiService:           aiService,
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

		// Fetch User to determine Mode
		user, err := s.userRepo.GetByID(ctx, position.UserID)
		if err != nil {
			log.Printf("ERROR: Failed to get user %s: %v", position.UserID, err)
			continue
		}

		// === REAL TRADING CLOSE LOGIC ===
		exitPrice := currentPrice // Default to trigger price
		if user.Mode == domain.ModeReal {
			// Determine opposite side
			closeSide := "SELL"
			if position.Side == "SHORT" {
				closeSide = "BUY"
			}

			// Execute Real Close
			res, err := s.aiService.ExecuteClose(ctx, position.Symbol, closeSide, position.Size)
			if err != nil {
				log.Printf("[ERR] VirtualBroker: FAILED to execute REAL CLOSE for %s: %v", position.Symbol, err)
				continue // Don't close position in DB if execution failed
			}
			exitPrice = res.AvgPrice // Use actual execution price
			log.Printf("[Broker] REAL CLOSE SUCCESS: %s @ %.4f", position.Symbol, exitPrice)
		}

		// Calculate PnL with fees using Exit Price
		netPnL := s.calculateNetPnL(position, exitPrice)
		pnlPercent := position.CalculatePnLPercent(exitPrice)

		// Close position in DB
		now := time.Now()
		position.ExitPrice = &exitPrice
		position.PnL = &netPnL
		position.PnLPercent = &pnlPercent
		position.ClosedBy = &closedBy
		position.Status = status
		position.ClosedAt = &now

		if err := s.positionRepo.Update(ctx, position); err != nil {
			log.Printf("ERROR: Failed to update position %s: %v", position.ID, err)
			continue
		}

		// Update user balance (ONLY PAPER MODE)
		if user.Mode == domain.ModePaper {
			newBalance := user.PaperBalance + netPnL
			if err := s.userRepo.UpdateBalance(ctx, user.ID, newBalance, domain.ModePaper); err != nil {
				log.Printf("ERROR: Failed to update user balance: %v", err)
				continue
			}
		}

		// --- NOTIFICATION & SIGNAL UPDATE LOGIC ---
		// Determine result string for Signal Review
		reviewResult := "WIN"
		if netPnL < 0 {
			reviewResult = "LOSS"
			position.Status = domain.StatusClosedLoss
		} else {
			position.Status = domain.StatusClosedWin
		}

		// Update Signal in DB if attached
		if position.SignalID != nil {
			if err := s.signalRepo.UpdateReviewStatus(ctx, *position.SignalID, reviewResult, &pnlPercent); err != nil {
				log.Printf("WARNING: Failed to update signal review status: %v", err)
			}

			// Send Notification
			if s.notificationService != nil {
				if sig, err := s.signalRepo.GetByID(ctx, *position.SignalID); err == nil {
					sig.ReviewResult = &reviewResult
					if err := s.notificationService.SendReview(*sig, &netPnL); err != nil {
						log.Printf("WARNING: Failed to send auto-close notification: %v", err)
					}
				}
			}
		}

		log.Printf("[OK] Position CLOSED: %s %s | Entry=%.2f Exit=%.2f | PnL=%.2f USDT | Status=%s",
			position.Symbol, position.Side, position.EntryPrice, exitPrice, netPnL, status)
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

	// Calculate fees using Binance Futures taker fee (0.04% for market orders)
	// Both entry and exit are market orders, so use taker fee
	feeRate := TradingFeeTakerPercent / 100.0 // Convert 0.04% to 0.0004
	entryFee := position.Size * position.EntryPrice * feeRate
	exitFee := position.Size * exitPrice * feeRate
	totalFees := entryFee + exitFee

	// Net PnL = Gross PnL - Fees
	netPnL := grossPnL - totalFees

	log.Printf("   PnL Calculation for %s:", position.Symbol)
	log.Printf("   - Gross PnL: %.4f USDT", grossPnL)
	log.Printf("   - Entry Fee (0.04%% taker): %.4f USDT", entryFee)
	log.Printf("   - Exit Fee (0.04%% taker): %.4f USDT", exitFee)
	log.Printf("   - Total Fees: %.4f USDT", totalFees)
	log.Printf("   - Net PnL: %.4f USDT", netPnL)

	return netPnL
}
