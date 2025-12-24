package usecase

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/google/uuid"

	"neurotrade/internal/domain"
)

// TradingService handles core trading logic
type TradingService struct {
	aiService    domain.AIService
	signalRepo   domain.SignalRepository
	minConfidence int
}

// NewTradingService creates a new TradingService
func NewTradingService(
	aiService domain.AIService,
	signalRepo domain.SignalRepository,
	minConfidence int,
) *TradingService {
	return &TradingService{
		aiService:    aiService,
		signalRepo:   signalRepo,
		minConfidence: minConfidence,
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

		// Save to database
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
