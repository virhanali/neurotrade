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
		log.Println("[WARN] Market scan skipped: Previous scan still running")
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
		log.Printf("[OK] Saved High Confidence Signal: %s | %s | Confidence: %d%% | Entry: %.4f | SL: %.4f | TP: %.4f",
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

	// Convert screener metrics for ML feedback loop
	if aiSignal.ScreenerMetrics != nil {
		signal.ScreenerMetrics = convertScreenerMetrics(aiSignal.ScreenerMetrics)
	}

	return signal
}

// convertScreenerMetrics converts map to ScreenerMetrics struct
func convertScreenerMetrics(m map[string]interface{}) *domain.ScreenerMetrics {
	getFloat := func(key string) float64 {
		if v, ok := m[key]; ok {
			switch val := v.(type) {
			case float64:
				return val
			case int:
				return float64(val)
			case int64:
				return float64(val)
			}
		}
		return 0
	}

	getBool := func(key string) bool {
		if v, ok := m[key]; ok {
			if b, ok := v.(bool); ok {
				return b
			}
		}
		return false
	}

	return &domain.ScreenerMetrics{
		ADX:        getFloat("adx"),
		VolZScore:  getFloat("vol_z_score"),
		KER:        getFloat("efficiency_ratio"),
		IsSqueeze:  getBool("is_squeeze"),
		Score:      getFloat("score"),
		VolRatio:   getFloat("vol_ratio"),
		ATRPercent: getFloat("atr_pct"),
	}
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

	// === BALANCE PROTECTION ===
	// Check if user has sufficient balance before creating position
	requiredMargin := user.FixedOrderSize
	if requiredMargin <= 0 {
		requiredMargin = tradeParams.PositionSizeUSDT
	}
	if requiredMargin <= 0 {
		requiredMargin = 30.0 // Default fallback
	}

	switch user.Mode {
	case "PAPER":
		// Paper trading: Check paper balance
		if user.PaperBalance < requiredMargin {
			log.Printf("[WARN] Insufficient PAPER balance for %s: Balance=%.2f, Required=%.2f. Skipping order.",
				user.Username, user.PaperBalance, requiredMargin)
			return fmt.Errorf("insufficient paper balance: have %.2f, need %.2f", user.PaperBalance, requiredMargin)
		}
	case "REAL":
		// Real trading: Check real balance (cached from Binance)
		if user.RealBalanceCache != nil && *user.RealBalanceCache < requiredMargin {
			log.Printf("[WARN] Insufficient REAL balance for %s: Balance=%.2f, Required=%.2f. Blocking order.",
				user.Username, *user.RealBalanceCache, requiredMargin)
			return fmt.Errorf("insufficient real balance: have %.2f, need %.2f", *user.RealBalanceCache, requiredMargin)
		}
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

	leverage := user.Leverage
	if leverage <= 0 {
		leverage = 20.0 // Default fallback
	}

	// entrySizeUSDT is treated as INITIAL MARGIN (User's Equity)
	// Calculate total position value (Notional)
	totalNotionalValue := entrySizeUSDT * leverage

	positionSize := (entrySizeUSDT * leverage) / signal.EntryPrice

	// === REAL TRADING EXECUTION ===
	if user.Mode == "REAL" {
		log.Printf("[REAL] Executing Entry for %s: %s %s Notional: %.2f USDT (Margin: %.2f)",
			user.Username, signal.Symbol, side, totalNotionalValue, entrySizeUSDT)

		// Pass TOTAL NOTIONAL VALUE to Python Executor
		execResult, err := ts.aiService.ExecuteEntry(ctx, signal.Symbol, side, totalNotionalValue, int(leverage))
		if err != nil {
			return fmt.Errorf("REAL ORDER FAILED for %s: %w", signal.Symbol, err)
		}

		// Update position details with REAL execution data
		signal.EntryPrice = execResult.AvgPrice
		positionSize = execResult.ExecutedQty
		log.Printf("[REAL] Order Filled: %s | Price: %.4f | Qty: %.4f", execResult.OrderID, execResult.AvgPrice, execResult.ExecutedQty)
	}

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
		Leverage:   leverage, // Store leverage for accurate PnL calculations
		Status:     initialStatus,
		CreatedAt:  time.Now(),
	}

	// Save position to database
	if err := ts.positionRepo.Save(ctx, position); err != nil {
		return fmt.Errorf("failed to save paper position: %w", err)
	}

	log.Printf("[TARGET] Auto-created Paper Position for %s: %s | Size: %.6f",
		user.Username, position.Symbol, position.Size)

	// Update signal status to EXECUTED
	if signal.ID != uuid.Nil {
		if err := ts.signalRepo.UpdateStatus(ctx, signal.ID, domain.StatusExecuted); err != nil {
			log.Printf("WARNING: Failed to update signal status: %v", err)
		}
	}

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

	// Fetch user to check MODE (REAL/PAPER)
	user, err := ts.userRepo.GetByID(ctx, position.UserID)
	if err != nil {
		return fmt.Errorf("failed to get user: %w", err)
	}

	// Check if already closed
	if position.Status != domain.StatusOpen {
		return fmt.Errorf("position is already closed")
	}

	// Calculate PnL
	currentPrice := 0.0

	// === REAL TRADING CLOSE ===
	if user.Mode == "REAL" {
		// Determine opposite side for closing
		closeSide := domain.SideShort // Close Long = Sell
		if position.Side == domain.SideShort {
			closeSide = domain.SideLong // Close Short = Buy
		}

		log.Printf("[REAL] Closing Position for %s: %s %s", user.Username, position.Symbol, closeSide)
		execResult, err := ts.aiService.ExecuteClose(ctx, position.Symbol, closeSide, position.Size)
		if err != nil {
			return fmt.Errorf("REAL CLOSE FAILED for %s: %w", position.Symbol, err)
		}

		currentPrice = execResult.AvgPrice
		log.Printf("[REAL] Close Filled: %s | Price: %.4f", execResult.OrderID, currentPrice)
	} else {
		// Paper Trading: Fetch real-time price
		price, err := ts.priceService.FetchSinglePrice(ctx, position.Symbol)
		if err != nil {
			log.Printf("WARNING: Failed to fetch price for closing %s, using entry price: %v", position.Symbol, err)
			price = position.EntryPrice
		}
		currentPrice = price
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

	// Update user balance (user struct already fetched above)
	// Re-fetch strictly not needed unless balance changed mid-process, but safe to use `user` from earlier

	newBalance := user.PaperBalance + pnl
	if err := ts.userRepo.UpdateBalance(ctx, position.UserID, newBalance, domain.ModePaper); err != nil {
		return fmt.Errorf("failed to update balance: %w", err)
	}

	// Determine result
	resultStatus := "LOSS"
	if pnl > 0 {
		resultStatus = "WIN"
	}

	// Calculate PnL percentage
	pnlPercent := position.CalculatePnLPercent(exitPrice)

	// Fetch signal for metrics and status update
	var sig *domain.Signal
	if position.SignalID != nil {
		sig, _ = ts.signalRepo.GetByID(ctx, *position.SignalID)

		// Update Signal Review Result & PnL
		if sig != nil {
			if err := ts.signalRepo.UpdateReviewStatus(ctx, sig.ID, resultStatus, &pnlPercent); err != nil {
				log.Printf("WARNING: Failed to update signal status on manual close: %v", err)
			}
		}
	}

	// Send ML Feedback to Python Engine (async, non-blocking)
	go func() {
		feedbackCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		feedback := &domain.FeedbackData{
			Symbol:  position.Symbol,
			Outcome: resultStatus,
			PnL:     pnlPercent,
		}

		// Attach screener metrics if available from signal
		if sig != nil && sig.ScreenerMetrics != nil {
			feedback.Metrics = sig.ScreenerMetrics
		}

		if err := ts.aiService.SendFeedback(feedbackCtx, feedback); err != nil {
			log.Printf("[WARN] Failed to send ML feedback: %v", err)
		}
	}()

	// Send Notification
	if ts.notificationService != nil && sig != nil {
		sig.ReviewResult = &resultStatus
		if err := ts.notificationService.SendReview(*sig, &pnl); err != nil {
			log.Printf("WARNING: Failed to send close notification: %v", err)
		}
	}

	log.Printf("[OK] Manually Closed position %s %s | PnL: %.2f USDT", position.Symbol, position.Side, pnl)
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

	log.Printf("[OK] Position Approved: %s %s", position.Symbol, position.Side)

	// Update associated signal status to EXECUTED
	if position.SignalID != nil {
		if err := ts.signalRepo.UpdateStatus(ctx, *position.SignalID, domain.StatusExecuted); err != nil {
			log.Printf("WARNING: Failed to update signal status on approval: %v", err)
		}
	}

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

	log.Printf("[ERROR] Position Declined: %s %s", position.Symbol, position.Side)

	// Update associated signal status to REJECTED
	if position.SignalID != nil {
		if err := ts.signalRepo.UpdateStatus(ctx, *position.SignalID, domain.StatusRejected); err != nil {
			log.Printf("WARNING: Failed to update signal status on decline: %v", err)
		}
	}

	return nil
}
