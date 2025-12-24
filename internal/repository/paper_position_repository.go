package repository

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"neurotrade/internal/domain"
)

// PaperPositionRepositoryImpl implements the PaperPositionRepository interface
type PaperPositionRepositoryImpl struct {
	db *pgxpool.Pool
}

// NewPaperPositionRepository creates a new PaperPositionRepository
func NewPaperPositionRepository(db *pgxpool.Pool) domain.PaperPositionRepository {
	return &PaperPositionRepositoryImpl{db: db}
}

// Save creates a new paper position
func (r *PaperPositionRepositoryImpl) Save(ctx context.Context, position *domain.PaperPosition) error {
	query := `
		INSERT INTO paper_positions (
			id, user_id, signal_id, symbol, side, entry_price,
			sl_price, tp_price, size, status, created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
		)
	`

	_, err := r.db.Exec(ctx, query,
		position.ID,
		position.UserID,
		position.SignalID,
		position.Symbol,
		position.Side,
		position.EntryPrice,
		position.SLPrice,
		position.TPPrice,
		position.Size,
		position.Status,
		position.CreatedAt,
	)

	if err != nil {
		return fmt.Errorf("failed to save paper position: %w", err)
	}

	return nil
}

// GetByUserID retrieves all positions for a user
func (r *PaperPositionRepositoryImpl) GetByUserID(ctx context.Context, userID uuid.UUID) ([]*domain.PaperPosition, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, exit_price, pnl, status,
		       created_at, closed_at
		FROM paper_positions
		WHERE user_id = $1
		ORDER BY created_at DESC
	`

	rows, err := r.db.Query(ctx, query, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to query positions by user ID: %w", err)
	}
	defer rows.Close()

	var positions []*domain.PaperPosition
	for rows.Next() {
		position := &domain.PaperPosition{}
		err := rows.Scan(
			&position.ID,
			&position.UserID,
			&position.SignalID,
			&position.Symbol,
			&position.Side,
			&position.EntryPrice,
			&position.SLPrice,
			&position.TPPrice,
			&position.Size,
			&position.ExitPrice,
			&position.PnL,
			&position.Status,
			&position.CreatedAt,
			&position.ClosedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan position: %w", err)
		}
		positions = append(positions, position)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating positions: %w", err)
	}

	return positions, nil
}

// GetOpenPositions retrieves all open positions across all users
func (r *PaperPositionRepositoryImpl) GetOpenPositions(ctx context.Context) ([]*domain.PaperPosition, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, exit_price, pnl, status,
		       created_at, closed_at
		FROM paper_positions
		WHERE status = 'OPEN'
		ORDER BY created_at ASC
	`

	rows, err := r.db.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to query open positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.PaperPosition
	for rows.Next() {
		position := &domain.PaperPosition{}
		err := rows.Scan(
			&position.ID,
			&position.UserID,
			&position.SignalID,
			&position.Symbol,
			&position.Side,
			&position.EntryPrice,
			&position.SLPrice,
			&position.TPPrice,
			&position.Size,
			&position.ExitPrice,
			&position.PnL,
			&position.Status,
			&position.CreatedAt,
			&position.ClosedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan position: %w", err)
		}
		positions = append(positions, position)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating positions: %w", err)
	}

	return positions, nil
}

// Update updates position status, exit price, and PnL
func (r *PaperPositionRepositoryImpl) Update(ctx context.Context, position *domain.PaperPosition) error {
	query := `
		UPDATE paper_positions
		SET exit_price = $1,
		    pnl = $2,
		    status = $3,
		    closed_at = $4
		WHERE id = $5
	`

	_, err := r.db.Exec(ctx, query,
		position.ExitPrice,
		position.PnL,
		position.Status,
		position.ClosedAt,
		position.ID,
	)

	if err != nil {
		return fmt.Errorf("failed to update paper position: %w", err)
	}

	return nil
}

// GetByID retrieves a position by ID
func (r *PaperPositionRepositoryImpl) GetByID(ctx context.Context, id uuid.UUID) (*domain.PaperPosition, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, exit_price, pnl, status,
		       created_at, closed_at
		FROM paper_positions
		WHERE id = $1
	`

	position := &domain.PaperPosition{}
	err := r.db.QueryRow(ctx, query, id).Scan(
		&position.ID,
		&position.UserID,
		&position.SignalID,
		&position.Symbol,
		&position.Side,
		&position.EntryPrice,
		&position.SLPrice,
		&position.TPPrice,
		&position.Size,
		&position.ExitPrice,
		&position.PnL,
		&position.Status,
		&position.CreatedAt,
		&position.ClosedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get position by ID: %w", err)
	}

	return position, nil
}
