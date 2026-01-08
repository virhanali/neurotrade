package repository

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"neurotrade/internal/domain"
)

// UserRepositoryImpl implements the UserRepository interface
type UserRepositoryImpl struct {
	db *pgxpool.Pool
}

// NewUserRepository creates a new UserRepository
func NewUserRepository(db *pgxpool.Pool) domain.UserRepository {
	return &UserRepositoryImpl{db: db}
}

// Create creates a new user
func (r *UserRepositoryImpl) Create(ctx context.Context, user *domain.User) error {
	query := `
		INSERT INTO users (
			id, username, password_hash, role,
			paper_balance, mode, is_auto_trade_enabled, fixed_order_size, leverage, created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10
		)
	`

	_, err := r.db.Exec(ctx, query,
		user.ID,
		user.Username,
		user.PasswordHash,
		user.Role,
		user.PaperBalance,
		user.Mode,
		user.IsAutoTradeEnabled,
		user.FixedOrderSize,
		user.Leverage,
		user.CreatedAt,
	)

	if err != nil {
		return fmt.Errorf("failed to create user: %w", err)
	}

	return nil
}

// GetByID retrieves a user by ID
func (r *UserRepositoryImpl) GetByID(ctx context.Context, id uuid.UUID) (*domain.User, error) {
	query := `
		SELECT id, username, password_hash, role,
		       paper_balance, real_balance_cache, mode, is_auto_trade_enabled, fixed_order_size, leverage, 
               COALESCE(binance_api_key, ''), COALESCE(binance_api_secret, ''), created_at, updated_at
		FROM users
		WHERE id = $1
	`

	user := &domain.User{}
	err := r.db.QueryRow(ctx, query, id).Scan(
		&user.ID,
		&user.Username,
		&user.PasswordHash,
		&user.Role,
		&user.PaperBalance,
		&user.RealBalanceCache,
		&user.Mode,
		&user.IsAutoTradeEnabled,
		&user.FixedOrderSize,
		&user.Leverage,
		&user.BinanceAPIKey,
		&user.BinanceAPISecret,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get user by ID: %w", err)
	}

	return user, nil
}

// GetByUsername retrieves a user by username
func (r *UserRepositoryImpl) GetByUsername(ctx context.Context, username string) (*domain.User, error) {
	query := `
		SELECT id, username, password_hash, role,
		       paper_balance, real_balance_cache, mode, is_auto_trade_enabled, fixed_order_size, leverage, 
               COALESCE(binance_api_key, ''), COALESCE(binance_api_secret, ''), created_at, updated_at
		FROM users
		WHERE username = $1
	`

	user := &domain.User{}
	err := r.db.QueryRow(ctx, query, username).Scan(
		&user.ID,
		&user.Username,
		&user.PasswordHash,
		&user.Role,
		&user.PaperBalance,
		&user.RealBalanceCache,
		&user.Mode,
		&user.IsAutoTradeEnabled,
		&user.FixedOrderSize,
		&user.Leverage,
		&user.BinanceAPIKey,
		&user.BinanceAPISecret,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get user by username: %w", err)
	}

	return user, nil
}

// UpdateBalance updates user's balance
func (r *UserRepositoryImpl) UpdateBalance(ctx context.Context, userID uuid.UUID, balance float64, mode string) error {
	var query string

	if mode == domain.ModeReal {
		query = `
			UPDATE users
			SET real_balance_cache = $1, updated_at = NOW()
			WHERE id = $2
		`
	} else {
		// Default to PAPER
		query = `
			UPDATE users
			SET paper_balance = $1, updated_at = NOW()
			WHERE id = $2
		`
	}

	_, err := r.db.Exec(ctx, query, balance, userID)
	if err != nil {
		return fmt.Errorf("failed to update user balance (mode=%s): %w", mode, err)
	}

	return nil
}

// GetAll retrieves all users
func (r *UserRepositoryImpl) GetAll(ctx context.Context) ([]*domain.User, error) {
	query := `
		SELECT id, username, password_hash, role,
		       paper_balance, real_balance_cache, mode, is_auto_trade_enabled, fixed_order_size, leverage, 
		       COALESCE(binance_api_key, ''), COALESCE(binance_api_secret, ''), created_at, updated_at
		FROM users
		ORDER BY created_at ASC
	`

	rows, err := r.db.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to query all users: %w", err)
	}
	defer rows.Close()

	var users []*domain.User
	for rows.Next() {
		user := &domain.User{}
		err := rows.Scan(
			&user.ID,
			&user.Username,
			&user.PasswordHash,
			&user.Role,
			&user.PaperBalance,
			&user.RealBalanceCache,
			&user.Mode,
			&user.IsAutoTradeEnabled,
			&user.FixedOrderSize,
			&user.Leverage,
			&user.BinanceAPIKey,
			&user.BinanceAPISecret,
			&user.CreatedAt,
			&user.UpdatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan user: %w", err)
		}
		users = append(users, user)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating users: %w", err)
	}

	return users, nil
}

// UpdateAutoTradeStatus updates the auto-trade flag for a user
func (r *UserRepositoryImpl) UpdateAutoTradeStatus(ctx context.Context, userID uuid.UUID, enabled bool) error {
	query := `
		UPDATE users
		SET is_auto_trade_enabled = $1, updated_at = NOW()
		WHERE id = $2
	`

	_, err := r.db.Exec(ctx, query, enabled, userID)
	if err != nil {
		return fmt.Errorf("failed to update auto-trade status: %w", err)
	}

	return nil
}

// UpdateSettings updates user trading settings
func (r *UserRepositoryImpl) UpdateSettings(ctx context.Context, user *domain.User) error {
	query := `
		UPDATE users
		SET mode = $1, fixed_order_size = $2, leverage = $3, is_auto_trade_enabled = $4, 
            binance_api_key = $5, binance_api_secret = $6, updated_at = NOW()
		WHERE id = $7
	`

	_, err := r.db.Exec(ctx, query,
		user.Mode,
		user.FixedOrderSize,
		user.Leverage,
		user.IsAutoTradeEnabled,
		user.BinanceAPIKey,
		user.BinanceAPISecret,
		user.ID,
	)

	if err != nil {
		return fmt.Errorf("failed to update user settings: %w", err)
	}

	return nil
}

// UpdateRealBalance updates cached real wallet balance from Binance
func (r *UserRepositoryImpl) UpdateRealBalance(ctx context.Context, userID uuid.UUID, balance float64) error {
	query := `
		UPDATE users
		SET real_balance_cache = $1, updated_at = NOW()
		WHERE id = $2
	`

	_, err := r.db.Exec(ctx, query, balance, userID)
	if err != nil {
		return fmt.Errorf("failed to update real balance cache: %w", err)
	}

	return nil
}
