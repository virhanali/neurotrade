package domain

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// PaperPosition represents a paper trading position
type PaperPosition struct {
	ID         uuid.UUID  `json:"id"`
	UserID     uuid.UUID  `json:"user_id"`
	SignalID   *uuid.UUID `json:"signal_id,omitempty"`
	Symbol     string     `json:"symbol"`
	Side       string     `json:"side"`
	EntryPrice float64    `json:"entry_price"`
	SLPrice    float64    `json:"sl_price"`
	TPPrice    float64    `json:"tp_price"`
	Size       float64    `json:"size"`     // Position size in base asset (e.g., BTC, ETH)
	Leverage   float64    `json:"leverage"` // Leverage used for this position
	ExitPrice  *float64   `json:"exit_price,omitempty"`
	PnL        *float64   `json:"pnl,omitempty"`         // PnL in USD
	PnLPercent *float64   `json:"pnl_percent,omitempty"` // PnL as percentage (with leverage)
	Status     string     `json:"status"`
	ClosedBy   *string    `json:"closed_by,omitempty"` // TP, SL, TRAILING, MANUAL
	CreatedAt  time.Time  `json:"created_at"`
	ClosedAt   *time.Time `json:"closed_at,omitempty"`
}

// PositionSide constants
const (
	SideLong  = "LONG"
	SideShort = "SHORT"
)

// PositionStatus constants
const (
	StatusOpen                    = "OPEN"
	StatusClosedWin               = "CLOSED_WIN"
	StatusClosedLoss              = "CLOSED_LOSS"
	StatusClosedManual            = "CLOSED_MANUAL"
	StatusPositionPendingApproval = "PENDING_APPROVAL"
	StatusPositionRejected        = "REJECTED"
)

// ClosedBy constants (how the position was closed)
const (
	ClosedByTP       = "TP"       // Take Profit hit
	ClosedBySL       = "SL"       // Stop Loss hit
	ClosedByTrailing = "TRAILING" // Trailing Stop hit
	ClosedByManual   = "MANUAL"   // Manually closed by user
)

// PaperPositionRepository defines the interface for paper position operations
type PaperPositionRepository interface {
	// Save creates a new paper position
	Save(ctx context.Context, position *PaperPosition) error

	// GetByUserID retrieves all positions for a user
	GetByUserID(ctx context.Context, userID uuid.UUID) ([]*PaperPosition, error)

	// GetOpenPositions retrieves all open positions (across all users or specific user)
	GetOpenPositions(ctx context.Context) ([]*PaperPosition, error)

	// Update updates position status, exit price, and PnL
	Update(ctx context.Context, position *PaperPosition) error

	// GetByID retrieves a position by ID
	GetByID(ctx context.Context, id uuid.UUID) (*PaperPosition, error)

	// GetTodayRealizedPnL retrieves the realized PnL for positions closed today (WIB)
	GetTodayRealizedPnL(ctx context.Context, userID uuid.UUID, startOfDay time.Time) (float64, error)

	// GetPnLBySignalIDs retrieves PnL values for a list of signal IDs
	GetPnLBySignalIDs(ctx context.Context, signalIDs []uuid.UUID) (map[uuid.UUID]float64, error)

	// GetClosedPositionsHistory retrieves closed positions for chart data
	GetClosedPositionsHistory(ctx context.Context, userID uuid.UUID, limit int) ([]PnLHistoryEntry, error)

	// GetClosedPositionsHistorySince retrieves closed positions since a specific time
	GetClosedPositionsHistorySince(ctx context.Context, userID uuid.UUID, since time.Time, limit int) ([]PnLHistoryEntry, error)

	// GetClosedPositions retrieves detailed closed positions
	GetClosedPositions(ctx context.Context, userID uuid.UUID, limit int) ([]*PaperPosition, error)
}

// PnLHistoryEntry represents a data point for PnL charting
type PnLHistoryEntry struct {
	ClosedAt time.Time
	PnL      float64
}

// IsLong checks if the position is a LONG position
func (p *PaperPosition) IsLong() bool {
	return p.Side == SideLong || p.Side == "BUY"
}

// CalculateGrossPnL calculates the gross PnL (before fees) based on current price
func (p *PaperPosition) CalculateGrossPnL(currentPrice float64) float64 {
	if p.IsLong() {
		return (currentPrice - p.EntryPrice) * p.Size
	}
	// Short
	return (p.EntryPrice - currentPrice) * p.Size
}

// CalculatePnLPercent calculates the PnL percentage based on current price
func (p *PaperPosition) CalculatePnLPercent(currentPrice float64) float64 {
	if p.EntryPrice == 0 {
		return 0
	}
	if p.IsLong() {
		return ((currentPrice - p.EntryPrice) / p.EntryPrice) * 100
	}
	// Short
	return ((p.EntryPrice - currentPrice) / p.EntryPrice) * 100
}

// CheckSLTP checks if SL or TP is hit and returns how it was closed
func (p *PaperPosition) CheckSLTP(currentPrice float64) (shouldClose bool, status string, closedBy string) {
	if p.IsLong() {
		if currentPrice <= p.SLPrice {
			return true, StatusClosedLoss, ClosedBySL
		}
		if currentPrice >= p.TPPrice {
			return true, StatusClosedWin, ClosedByTP
		}
	} else {
		if currentPrice >= p.SLPrice {
			return true, StatusClosedLoss, ClosedBySL
		}
		if currentPrice <= p.TPPrice {
			return true, StatusClosedWin, ClosedByTP
		}
	}
	return false, StatusOpen, ""
}
