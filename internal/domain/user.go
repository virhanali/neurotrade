package domain

import (
	"time"

	"github.com/google/uuid"
)

// User represents a user in the system
type User struct {
	ID                 uuid.UUID `json:"id"`
	Username           string    `json:"username"`
	PasswordHash       string    `json:"-"` // Never expose password hash in JSON
	Role               string    `json:"role"`
	Mode               string    `json:"mode"`
	PaperBalance       float64   `json:"paper_balance"`
	RealBalanceCache   *float64  `json:"real_balance_cache,omitempty"`
	MaxDailyLoss       float64   `json:"max_daily_loss"`
	IsAutoTradeEnabled bool      `json:"is_auto_trade_enabled"`
	CreatedAt          time.Time `json:"created_at"`
	UpdatedAt          time.Time `json:"updated_at"`
}

// UserRole constants
const (
	RoleAdmin = "ADMIN"
	RoleUser  = "USER"
)

// TradingMode constants
const (
	ModePaper = "PAPER"
	ModeReal  = "REAL"
)
