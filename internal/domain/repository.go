package domain

import (
	"context"

	"github.com/google/uuid"
)

// SignalRepository defines the interface for signal data operations
type SignalRepository interface {
	// Save saves a new signal to the database
	Save(ctx context.Context, signal *Signal) error

	// GetRecent retrieves the most recent signals
	GetRecent(ctx context.Context, limit int) ([]*Signal, error)

	// GetByID retrieves a signal by its ID
	GetByID(ctx context.Context, id uuid.UUID) (*Signal, error)

	// GetBySymbol retrieves signals for a specific symbol
	GetBySymbol(ctx context.Context, symbol string, limit int) ([]*Signal, error)

	// UpdateStatus updates the status of a signal
	UpdateStatus(ctx context.Context, id uuid.UUID, status string) error
}

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
}

// PaperPositionRepository defines the interface for paper position operations
type PaperPositionRepository interface {
	// Create creates a new paper position
	Create(ctx context.Context, position *PaperPosition) error

	// GetByUserID retrieves all positions for a user
	GetByUserID(ctx context.Context, userID uuid.UUID) ([]*PaperPosition, error)

	// GetOpenPositions retrieves all open positions for a user
	GetOpenPositions(ctx context.Context, userID uuid.UUID) ([]*PaperPosition, error)

	// Close closes a position and updates PnL
	Close(ctx context.Context, id uuid.UUID, pnl float64) error
}
