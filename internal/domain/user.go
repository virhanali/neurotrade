package domain

import (
	"context"
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
	FixedOrderSize     float64   `json:"fixed_order_size"`
	Leverage           float64   `json:"leverage"`
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

// UserRepository defines the interface for user data operations
type UserRepository interface {
	// Create creates a new user
	Create(ctx context.Context, user *User) error

	// GetByID retrieves a user by ID
	GetByID(ctx context.Context, id uuid.UUID) (*User, error)

	// GetByUsername retrieves a user by username
	GetByUsername(ctx context.Context, username string) (*User, error)

	// UpdateBalance updates user's balance
	UpdateBalance(ctx context.Context, userID uuid.UUID, balance float64, mode string) error
	// GetAll retrieves all users
	GetAll(ctx context.Context) ([]*User, error)

	// UpdateAutoTradeStatus updates the auto-trade flag for a user
	UpdateAutoTradeStatus(ctx context.Context, userID uuid.UUID, enabled bool) error

	// UpdateSettings updates user trading settings
	UpdateSettings(ctx context.Context, user *User) error

	// UpdateRealBalance updates cached real wallet balance from Binance
	UpdateRealBalance(ctx context.Context, userID uuid.UUID, balance float64) error
}
