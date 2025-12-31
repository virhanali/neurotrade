package domain

import (
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
	Size       float64    `json:"size"` // Position size in base asset (e.g., BTC, ETH)
	ExitPrice  *float64   `json:"exit_price,omitempty"`
	PnL        *float64   `json:"pnl,omitempty"`
	Status     string     `json:"status"`
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
	StatusOpen         = "OPEN"
	StatusClosedWin    = "CLOSED_WIN"
	StatusClosedLoss   = "CLOSED_LOSS"
	StatusClosedManual = "CLOSED_MANUAL"
)
