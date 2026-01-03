package usecase

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/google/uuid"

	"neurotrade/internal/domain"
)

// NotificationService defines the interface for sending notifications
type NotificationService interface {
	SendSignal(signal domain.Signal) error
	SendReview(signal domain.Signal, pnl *float64) error
}

// TradingService handles core trading logic
type TradingService struct {
	aiService           domain.AIService
	signalRepo          domain.SignalRepository
	positionRepo        domain.PaperPositionRepository
	userRepo            domain.UserRepository
	notificationService NotificationService
	priceService        domain.MarketPriceService
	minConfidence       int
	scanMu              sync.Mutex
	isScanning          bool
}

// NewTradingService creates a new TradingService
func NewTradingService(
	aiService domain.AIService,
	signalRepo domain.SignalRepository,
	positionRepo domain.PaperPositionRepository,
	userRepo domain.UserRepository,
	notificationService NotificationService,
	priceService domain.MarketPriceService,
	minConfidence int,
) *TradingService {
	return &TradingService{
		aiService:           aiService,
		signalRepo:          signalRepo,
		positionRepo:        positionRepo,
		userRepo:            userRepo,
		notificationService: notificationService,
		priceService:        priceService,
		minConfidence:       minConfidence,
	}
}

// ProcessMarketScan performs a complete market scan and saves high-confidence signals
// mode: "SCALPER" for M15 aggressive trading, "INVESTOR" for H1 trend following
func (ts *TradingService) ProcessMarketScan(ctx context.Context, balance float64, mode string) error {
	// Mutex Lock to prevent overlapping scans (Race Condition fix)
	ts.scanMu.Lock()
	if ts.isScanning {
		ts.scanMu.Unlock()
		log.Println("⚠️ Market scan skipped: Previous scan still running")
		return nil
	}
	ts.isScanning = true
	ts.scanMu.Unlock()

	// Ensure we release the flag when done
	defer func() {
		ts.scanMu.Lock()
		ts.isScanning = false
		ts.scanMu.Unlock()
	}()

	log.Printf("=== Starting Market Scan [Mode: %s] ===", mode)
	startTime := time.Now()

	// Step 1: Call Python AI Engine to analyze market
	log.Printf("Calling Python AI Engine for market analysis (Mode: %s)...", mode)
	aiSignals, err := ts.aiService.AnalyzeMarket(ctx, balance, mode)
	if err != nil {
		return fmt.Errorf("failed to analyze market: %w", err)
	}

	log.Printf("Received %d signals from AI Engine", len(aiSignals))

	// Get all eligible users for auto-trading
	users, err := ts.userRepo.GetAll(ctx)
	if err != nil {
		log.Printf("WARNING: Failed to fetch users for auto-trading: %v", err)
		// We still process signals to save them to DB
	}
	log.Printf("Found %d users for potential auto-trading", len(users))

	// Step 2: Process each signal
	savedCount := 0
	processedSymbols := make(map[string]bool)

	// Pre-fetch active positions to avoid duplicates
	activePositions, err := ts.positionRepo.GetOpenPositions(ctx)
	activeSymbolMap := make(map[string]bool)
	if err == nil {
		for _, pos := range activePositions {
			// Check if status is OPEN or PENDING_APPROVAL
			if pos.Status == domain.StatusOpen || pos.Status == domain.StatusPositionPendingApproval {
				activeSymbolMap[pos.Symbol] = true
			}
		}
	} else {
		log.Printf("WARNING: Failed to fetch open positions: %v", err)
	}

	for _, aiSignal := range aiSignals {
		// Dedup check 1: Prevent processing the same symbol twice in one batch
		if processedSymbols[aiSignal.Symbol] {
			continue
		}
		processedSymbols[aiSignal.Symbol] = true

		// Dedup check 2: Prevent processing if we already have an active position
		if activeSymbolMap[aiSignal.Symbol] {
			log.Printf("Skipping %s: Active position already exists", aiSignal.Symbol)
			continue
		}
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

		// Distribute signal to ALL users
		for _, user := range users {
			// Only create position if user is in PAPER mode (and later check for Enabled AutoTrade flag)
			if user.Mode != domain.ModePaper {
				continue
			}

			// Auto-create paper position for this user
			// We pass the specific user object now
			if err := ts.createPaperPositionForUser(ctx, user, signal, aiSignal.TradeParams); err != nil {
				log.Printf("WARNING: Failed to create paper position for user %s (%s): %v", user.Username, signal.Symbol, err)
			}
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

// createPaperPositionForUser automatically creates a paper trading position for a specific user
func (ts *TradingService) createPaperPositionForUser(ctx context.Context, user *domain.User, signal *domain.Signal, tradeParams *domain.TradeParams) error {
	if tradeParams == nil {
		return fmt.Errorf("trade params not available")
	}

	if signal.EntryPrice <= 0 {
		return fmt.Errorf("invalid entry price: %.4f", signal.EntryPrice)
	}

	// Determine position side based on signal type
	var side string
	switch signal.Type {
	case "LONG":
		side = domain.SideLong
	case "SHORT":
		side = domain.SideShort
	default:
		return fmt.Errorf("invalid signal type: %s", signal.Type)
	}

	// Calculate position size based on User Setting (DB Priority)
	// If user has set fixed_order_size (e.g., 30), usage that.
	// Otherwise fallback to AI suggestion.
	entrySizeUSDT := user.FixedOrderSize
	if entrySizeUSDT <= 0 {
		entrySizeUSDT = tradeParams.PositionSizeUSDT
	}
	// Safety net
	if entrySizeUSDT <= 0 {
		entrySizeUSDT = 30.0
	}

	// Apply Leverage from DB (User Setting)
	leverage := user.Leverage
	if leverage <= 0 {
		leverage = 20.0 // Default fallback
	}
	positionSize := (entrySizeUSDT * leverage) / signal.EntryPrice

	// Determine initial status based on Auto-Trade setting
	initialStatus := domain.StatusPositionPendingApproval
	if user.IsAutoTradeEnabled {
		initialStatus = domain.StatusOpen
	}

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
		Status:     initialStatus,
		CreatedAt:  time.Now(),
	}

	// Save position to database
	if err := ts.positionRepo.Save(ctx, position); err != nil {
		return fmt.Errorf("failed to save paper position: %w", err)
	}

	log.Printf("🎯 Auto-created Paper Position for %s: %s | Size: %.6f",
		user.Username, position.Symbol, position.Size)

	return nil
}

// ClosePosition closes a specific position manually
func (ts *TradingService) ClosePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID, isAdmin bool) error {
	// Get position
	position, err := ts.positionRepo.GetByID(ctx, positionID)
	if err != nil {
		return fmt.Errorf("failed to get position: %w", err)
	}

	// Verify ownership (unless admin)
	if position.UserID != userID && !isAdmin {
		return fmt.Errorf("unauthorized: position belongs to another user")
	}

	// Check if already closed
	if position.Status != domain.StatusOpen {
		return fmt.Errorf("position is already closed")
	}

	// Calculate PnL
	// Fetch real-time price for accurate PnL
	currentPrice, err := ts.priceService.FetchSinglePrice(ctx, position.Symbol)
	if err != nil {
		log.Printf("WARNING: Failed to fetch price for closing %s, using entry price: %v", position.Symbol, err)
		currentPrice = position.EntryPrice
	}

	exitPrice := currentPrice

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

	now := time.Now()
	position.ExitPrice = &exitPrice
	position.PnL = &pnl
	position.Status = domain.StatusClosedManual
	position.ClosedAt = &now

	if err := ts.positionRepo.Update(ctx, position); err != nil {
		return fmt.Errorf("failed to update position: %w", err)
	}

	// Update user balance
	user, err := ts.userRepo.GetByID(ctx, position.UserID)
	if err != nil {
		return fmt.Errorf("failed to get user: %w", err)
	}

	newBalance := user.PaperBalance + pnl
	if err := ts.userRepo.UpdateBalance(ctx, position.UserID, newBalance, domain.ModePaper); err != nil {
		return fmt.Errorf("failed to update balance: %w", err)
	}

	// Send Notification
	if ts.notificationService != nil {
		// Construct a manual signal/update for notification
		// We can reuse SendReview or make a new one. SendReview is good.
		// We need to fetch the original signal to pass to SendReview?
		// Or just construct a dummy one with enough info.
		// Let's try to fetch the signal if possible, otherwise mock it.
		if position.SignalID != nil {
			if sig, err := ts.signalRepo.GetByID(ctx, *position.SignalID); err == nil {
				// Mark signal as manually closed in DB immediately to prevent ReviewService from processing it
				manuallyClosed := "MANUAL_CLOSE"
				// We don't have a specific pnl percentage for the signal here readily available from position pnl (which is $)
				// But we can approximate or just leave pnl nil.
				// UpdateReviewStatus(ctx, id, status, pnl)
				if err := ts.signalRepo.UpdateReviewStatus(ctx, sig.ID, manuallyClosed, nil); err != nil {
					log.Printf("WARNING: Failed to update signal status to MANUAL_CLOSE: %v", err)
				}

				status := "MANUAL_CLOSE"
				sig.ReviewResult = &status // Custom status for notification logic

				if err := ts.notificationService.SendReview(*sig, &pnl); err != nil {
					log.Printf("WARNING: Failed to send close notification: %v", err)
				}
			}
		}
	}

	log.Printf("✓ Manually Closed position %s %s | PnL: %.2f USDT", position.Symbol, position.Side, pnl)
	return nil
}

// CloseAllPositions closes all open positions for a user (PANIC BUTTON)
func (ts *TradingService) CloseAllPositions(ctx context.Context, userID uuid.UUID) error {

	log.Printf("🚨 PANIC BUTTON TRIGGERED for user %s - Closing all positions", userID)

	positions, err := ts.positionRepo.GetByUserID(ctx, userID)
	if err != nil {
		return fmt.Errorf("failed to get user positions: %w", err)
	}

	closedCount := 0
	for _, position := range positions {
		if position.Status != domain.StatusOpen {
			continue // Skip already closed positions
		}

		// Reuse ClosePosition logic to ensure consistency and notifications
		// Note: Panic button is always "self" closing, so isAdmin=false is fine (or true to bypass check)
		// Since we verified userID above, we can pass it directly.
		if err := ts.ClosePosition(ctx, position.ID, userID, true); err != nil {
			log.Printf("ERROR: Failed to close position %s: %v", position.ID, err)
			continue
		}
		closedCount++
	}

	log.Printf("🚨 PANIC BUTTON COMPLETE: Closed %d positions", closedCount)
	return nil
}

// ApprovePosition approves a pending position
func (ts *TradingService) ApprovePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID) error {
	// Get position
	position, err := ts.positionRepo.GetByID(ctx, positionID)
	if err != nil {
		return fmt.Errorf("failed to get position: %w", err)
	}

	// Verify ownership
	if position.UserID != userID {
		return fmt.Errorf("unauthorized: position belongs to another user")
	}

	// Verify status
	if position.Status != domain.StatusPositionPendingApproval {
		return fmt.Errorf("position is not pending approval")
	}

	// Update status to OPEN
	position.Status = domain.StatusOpen

	if err := ts.positionRepo.Update(ctx, position); err != nil {
		return fmt.Errorf("failed to approve position: %w", err)
	}

	log.Printf("✅ Position Approved: %s %s", position.Symbol, position.Side)
	return nil
}

// DeclinePosition declines a pending position
func (ts *TradingService) DeclinePosition(ctx context.Context, positionID uuid.UUID, userID uuid.UUID) error {
	// Get position
	position, err := ts.positionRepo.GetByID(ctx, positionID)
	if err != nil {
		return fmt.Errorf("failed to get position: %w", err)
	}

	// Verify ownership
	if position.UserID != userID {
		return fmt.Errorf("unauthorized: position belongs to another user")
	}

	// Verify status
	if position.Status != domain.StatusPositionPendingApproval {
		return fmt.Errorf("position is not pending approval")
	}

	// Update status to REJECTED
	now := time.Now()
	position.Status = domain.StatusPositionRejected
	position.ClosedAt = &now

	if err := ts.positionRepo.Update(ctx, position); err != nil {
		return fmt.Errorf("failed to decline position: %w", err)
	}

	log.Printf("❌ Position Declined: %s %s", position.Symbol, position.Side)
	return nil
}
