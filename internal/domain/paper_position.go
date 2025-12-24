package domain

import (
	"time"

	"github.com/google/uuid"
)

// PaperPosition represents a paper trading position
type PaperPosition struct {
	ID         uuid.UUID  `json:"id"`
	UserID     uuid.UUID  `json:"user_id"`
	Symbol     string     `json:"symbol"`
	Side       string     `json:"side"`
	EntryPrice float64    `json:"entry_price"`
	SizeUSDT   float64    `json:"size_usdt"`
	SLPrice    float64    `json:"sl_price"`
	TPPrice    float64    `json:"tp_price"`
	Status     string     `json:"status"`
	PnL        *float64   `json:"pnl,omitempty"`
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
	PositionOpen   = "OPEN"
	PositionClosed = "CLOSED"
)
