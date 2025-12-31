package usecase

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/google/uuid"

	"neurotrade/internal/domain"
)

// NotificationService defines the interface for sending notifications
type NotificationService interface {
	SendSignal(signal domain.Signal) error
	SendReview(signal domain.Signal) error
}

// TradingService handles core trading logic
type TradingService struct {
	aiService           domain.AIService
	signalRepo          domain.SignalRepository
	positionRepo        domain.PaperPositionRepository
	userRepo            domain.UserRepository
	notificationService NotificationService
	minConfidence       int
	defaultUserID       uuid.UUID // For Phase 3, we'll use a default user (later will be per-user)
}

// NewTradingService creates a new TradingService
func NewTradingService(
	aiService domain.AIService,
	signalRepo domain.SignalRepository,
	positionRepo domain.PaperPositionRepository,
	userRepo domain.UserRepository,
	notificationService NotificationService,
	minConfidence int,
	defaultUserID uuid.UUID,
) *TradingService {
	return &TradingService{
		aiService:           aiService,
		signalRepo:          signalRepo,
		positionRepo:        positionRepo,
		userRepo:            userRepo,
		notificationService: notificationService,
		minConfidence:       minConfidence,
		defaultUserID:       defaultUserID,
	}
}

// ProcessMarketScan performs a complete market scan and saves high-confidence signals
func (ts *TradingService) ProcessMarketScan(ctx context.Context, balance float64) error {
	log.Println("=== Starting Market Scan ===")
	startTime := time.Now()

	// Step 1: Call Python AI Engine to analyze market
	log.Println("Calling Python AI Engine for market analysis...")
	aiSignals, err := ts.aiService.AnalyzeMarket(ctx, balance)
	if err != nil {
		return fmt.Errorf("failed to analyze market: %w", err)
	}

	log.Printf("Received %d signals from AI Engine", len(aiSignals))

	// Step 2: Process each signal
	savedCount := 0
	for _, aiSignal := range aiSignals {
		// Skip WAIT signals (not actionable)
		if aiSignal.FinalSignal == "WAIT" {
			log.Printf("Skipping %s: signal is WAIT (not actionable)", aiSignal.Symbol)
			continue
		}

		// Check confidence threshold
		if aiSignal.CombinedConfidence < ts.minConfidence {
			log.Printf("Skipping %s: confidence %d%% below threshold %d%%",
				aiSignal.Symbol, aiSignal.CombinedConfidence, ts.minConfidence)
			continue
		}

		// Create domain signal
		signal := ts.convertAISignalToDomain(aiSignal)

		// Save signal to database
		if err := ts.signalRepo.Save(ctx, signal); err != nil {
			log.Printf("ERROR: Failed to save signal for %s: %v", aiSignal.Symbol, err)
			continue
		}

		// Log success
		log.Printf("✓ Saved High Confidence Signal: %s | %s | Confidence: %d%% | Entry: %.4f | SL: %.4f | TP: %.4f",
			signal.Symbol,
			signal.Type,
			signal.Confidence,
			signal.EntryPrice,
			signal.SLPrice,
			signal.TPPrice,
		)

		// Send Telegram notification
		if ts.notificationService != nil {
			if err := ts.notificationService.SendSignal(*signal); err != nil {
				log.Printf("WARNING: Failed to send Telegram notification: %v", err)
			}
		}

		// Auto-create paper position for this signal
		if err := ts.createPaperPosition(ctx, signal, aiSignal.TradeParams, balance); err != nil {
			log.Printf("WARNING: Failed to create paper position for %s: %v", signal.Symbol, err)
			// Don't stop - signal is already saved
		}

		savedCount++
	}

	// Step 3: Log summary
	elapsed := time.Since(startTime)
	log.Println("=== Market Scan Complete ===")
	log.Printf("Total AI Signals: %d", len(aiSignals))
	log.Printf("Saved Signals: %d", savedCount)
	log.Printf("Execution Time: %.2f seconds", elapsed.Seconds())
	log.Println("===========================")

	return nil
}

// convertAISignalToDomain converts AI signal response to domain signal
func (ts *TradingService) convertAISignalToDomain(aiSignal *domain.AISignalResponse) *domain.Signal {
	signal := &domain.Signal{
		ID:         uuid.New(),
		Symbol:     aiSignal.Symbol,
		Type:       aiSignal.FinalSignal,
		Confidence: aiSignal.CombinedConfidence,
		Status:     domain.StatusPending,
		CreatedAt:  time.Now(),
	}

	// Build reasoning from both logic and vision analysis
	reasoning := fmt.Sprintf("Logic Analysis: %s\n\nVision Analysis: %s",
		aiSignal.LogicReasoning,
		aiSignal.VisionAnalysis,
	)
	signal.Reasoning = reasoning

	// Set trade parameters if available
	if aiSignal.TradeParams != nil {
		signal.EntryPrice = aiSignal.TradeParams.EntryPrice
		signal.SLPrice = aiSignal.TradeParams.StopLoss
		signal.TPPrice = aiSignal.TradeParams.TakeProfit
	}

	return signal
}

// GetRecentSignals retrieves recent trading signals
func (ts *TradingService) GetRecentSignals(ctx context.Context, limit int) ([]*domain.Signal, error) {
	return ts.signalRepo.GetRecent(ctx, limit)
}

// GetSignalsBySymbol retrieves signals for a specific symbol
func (ts *TradingService) GetSignalsBySymbol(ctx context.Context, symbol string, limit int) ([]*domain.Signal, error) {
	return ts.signalRepo.GetBySymbol(ctx, symbol, limit)
}

// createPaperPosition automatically creates a paper trading position for a high-confidence signal
func (ts *TradingService) createPaperPosition(ctx context.Context, signal *domain.Signal, tradeParams *domain.TradeParams, balance float64) error {
	if tradeParams == nil {
		return fmt.Errorf("trade params not available")
	}

	if signal.EntryPrice <= 0 {
		return fmt.Errorf("invalid entry price: %.4f", signal.EntryPrice)
	}

	// Get user to check if they're in PAPER mode
	if ts.defaultUserID == uuid.Nil {
		return fmt.Errorf("default user ID is not set (system initialization issue)")
	}

	user, err := ts.userRepo.GetByID(ctx, ts.defaultUserID)
	if err != nil {
		return fmt.Errorf("failed to get default user (%s): %w", ts.defaultUserID, err)
	}

	// Only create position if user is in PAPER mode
	if user.Mode != domain.ModePaper {
		log.Printf("Skipping paper position creation: user is in %s mode", user.Mode)
		return nil
	}

	// Determine position side based on signal type
	var side string
	if signal.Type == "LONG" {
		side = domain.SideLong
	} else if signal.Type == "SHORT" {
		side = domain.SideShort
	} else {
		return fmt.Errorf("invalid signal type: %s", signal.Type)
	}

	// Calculate position size in base asset (BTC, ETH, etc.)
	// Size = PositionSizeUSDT / EntryPrice
	positionSize := tradeParams.PositionSizeUSDT / signal.EntryPrice

	// Create paper position
	position := &domain.PaperPosition{
		ID:         uuid.New(),
		UserID:     user.ID,
		SignalID:   &signal.ID,
		Symbol:     signal.Symbol,
		Side:       side,
		EntryPrice: signal.EntryPrice,
		SLPrice:    signal.SLPrice,
		TPPrice:    signal.TPPrice,
		Size:       positionSize,
		Status:     domain.StatusOpen,
		CreatedAt:  time.Now(),
	}

	// Save position to database
	if err := ts.positionRepo.Save(ctx, position); err != nil {
		return fmt.Errorf("failed to save paper position: %w", err)
	}

	log.Printf("🎯 Auto-created Paper Position: %s %s | Size: %.6f | Entry: %.4f",
		position.Symbol, position.Side, position.Size, position.EntryPrice)

	return nil
}

// CloseAllPositions closes all open positions for a user (PANIC BUTTON)
func (ts *TradingService) CloseAllPositions(ctx context.Context, userIDStr string) error {
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		return fmt.Errorf("invalid user ID: %w", err)
	}

	log.Printf("🚨 PANIC BUTTON TRIGGERED for user %s - Closing all positions", userID)

	// Get all open positions for this user
	// Note: We need to add a method to get open positions by user ID
	// For now, we'll get all user positions and filter
	positions, err := ts.positionRepo.GetByUserID(ctx, userID)
	if err != nil {
		return fmt.Errorf("failed to get user positions: %w", err)
	}

	closedCount := 0
	for _, position := range positions {
		if position.Status != domain.StatusOpen {
			continue // Skip already closed positions
		}

		// Close position at current market price (simulate immediate close)
		now := time.Now()
		// In real implementation, we would fetch current market price
		// For panic button, we use entry price as exit (worst case scenario)
		exitPrice := position.EntryPrice

		// Calculate PnL (will be ~0 if using entry price)
		var pnl float64
		if position.Side == domain.SideLong {
			pnl = (exitPrice - position.EntryPrice) * position.Size
		} else {
			pnl = (position.EntryPrice - exitPrice) * position.Size
		}

		// Apply fees
		feeRate := 0.0005 // 0.05%
		entryFee := position.Size * position.EntryPrice * feeRate
		exitFee := position.Size * exitPrice * feeRate
		pnl = pnl - entryFee - exitFee

		// Update position
		position.ExitPrice = &exitPrice
		position.PnL = &pnl
		position.Status = domain.StatusClosedLoss // Panic close is usually a loss
		position.ClosedAt = &now

		if err := ts.positionRepo.Update(ctx, position); err != nil {
			log.Printf("ERROR: Failed to close position %s: %v", position.ID, err)
			continue
		}

		// Update user balance
		user, err := ts.userRepo.GetByID(ctx, userID)
		if err != nil {
			log.Printf("ERROR: Failed to get user for balance update: %v", err)
			continue
		}

		newBalance := user.PaperBalance + pnl
		if err := ts.userRepo.UpdateBalance(ctx, userID, newBalance, domain.ModePaper); err != nil {
			log.Printf("ERROR: Failed to update user balance: %v", err)
			continue
		}

		log.Printf("✓ Closed position %s %s | PnL: %.2f USDT", position.Symbol, position.Side, pnl)
		closedCount++
	}

	log.Printf("🚨 PANIC BUTTON COMPLETE: Closed %d positions", closedCount)
	return nil
}
