package repository

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"neurotrade/internal/domain"
)

// SignalRepositoryImpl implements the SignalRepository interface
type SignalRepositoryImpl struct {
	db *pgxpool.Pool
}

// NewSignalRepository creates a new SignalRepository
func NewSignalRepository(db *pgxpool.Pool) domain.SignalRepository {
	return &SignalRepositoryImpl{db: db}
}

// Save saves a new signal to the database
func (r *SignalRepositoryImpl) Save(ctx context.Context, signal *domain.Signal) error {
	query := `
		INSERT INTO signals (
			id, symbol, type, entry_price, sl_price, tp_price,
			confidence, reasoning, status, created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10
		)
	`

	_, err := r.db.Exec(ctx, query,
		signal.ID,
		signal.Symbol,
		signal.Type,
		signal.EntryPrice,
		signal.SLPrice,
		signal.TPPrice,
		signal.Confidence,
		signal.Reasoning,
		signal.Status,
		signal.CreatedAt,
	)

	if err != nil {
		return fmt.Errorf("failed to save signal: %w", err)
	}

	return nil
}

// UpsertPending updates an existing PENDING signal or creates a new one
// Returns true if created (INSERT), false if updated
func (r *SignalRepositoryImpl) UpsertPending(ctx context.Context, signal *domain.Signal) (bool, error) {
	// 1. Try to UPDATE existing PENDING signal for this symbol
	updateQuery := `
		UPDATE signals
		SET type = $1, entry_price = $2, sl_price = $3, tp_price = $4,
		    confidence = $5, reasoning = $6, created_at = $7
		WHERE symbol = $8 AND status = 'PENDING'
		RETURNING id
	`

	var existingID uuid.UUID
	err := r.db.QueryRow(ctx, updateQuery,
		signal.Type, signal.EntryPrice, signal.SLPrice, signal.TPPrice,
		signal.Confidence, signal.Reasoning, signal.CreatedAt,
		signal.Symbol,
	).Scan(&existingID)

	if err == nil {
		// Found and updated!
		signal.ID = existingID // Update ID in struct to match DB
		return false, nil      // False = Not New (Updated)
	}

	// 2. If Update failed (no rows), Insert new
	return true, r.Save(ctx, signal)
}

// GetRecent retrieves the most recent signals
func (r *SignalRepositoryImpl) GetRecent(ctx context.Context, limit int) ([]*domain.Signal, error) {
	query := `
		SELECT id, symbol, type, entry_price, sl_price, tp_price,
		       confidence, reasoning, status, review_result, review_pnl, created_at
		FROM signals
		ORDER BY created_at DESC
		LIMIT $1
	`

	rows, err := r.db.Query(ctx, query, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query recent signals: %w", err)
	}
	defer rows.Close()

	var signals []*domain.Signal
	for rows.Next() {
		signal := &domain.Signal{}
		err := rows.Scan(
			&signal.ID,
			&signal.Symbol,
			&signal.Type,
			&signal.EntryPrice,
			&signal.SLPrice,
			&signal.TPPrice,
			&signal.Confidence,
			&signal.Reasoning,
			&signal.Status,
			&signal.ReviewResult,
			&signal.ReviewPnL,
			&signal.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan signal: %w", err)
		}
		signals = append(signals, signal)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating signals: %w", err)
	}

	return signals, nil
}

// GetByID retrieves a signal by its ID
func (r *SignalRepositoryImpl) GetByID(ctx context.Context, id uuid.UUID) (*domain.Signal, error) {
	query := `
		SELECT id, symbol, type, entry_price, sl_price, tp_price,
		       confidence, reasoning, status, review_result, review_pnl, created_at
		FROM signals
		WHERE id = $1
	`

	signal := &domain.Signal{}
	err := r.db.QueryRow(ctx, query, id).Scan(
		&signal.ID,
		&signal.Symbol,
		&signal.Type,
		&signal.EntryPrice,
		&signal.SLPrice,
		&signal.TPPrice,
		&signal.Confidence,
		&signal.Reasoning,
		&signal.Status,
		&signal.ReviewResult,
		&signal.ReviewPnL,
		&signal.CreatedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get signal by ID: %w", err)
	}

	return signal, nil
}

// GetBySymbol retrieves signals for a specific symbol
func (r *SignalRepositoryImpl) GetBySymbol(ctx context.Context, symbol string, limit int) ([]*domain.Signal, error) {
	query := `
		SELECT id, symbol, type, entry_price, sl_price, tp_price,
		       confidence, reasoning, status, review_result, created_at
		FROM signals
		WHERE symbol = $1
		ORDER BY created_at DESC
		LIMIT $2
	`

	rows, err := r.db.Query(ctx, query, symbol, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query signals by symbol: %w", err)
	}
	defer rows.Close()

	var signals []*domain.Signal
	for rows.Next() {
		signal := &domain.Signal{}
		err := rows.Scan(
			&signal.ID,
			&signal.Symbol,
			&signal.Type,
			&signal.EntryPrice,
			&signal.SLPrice,
			&signal.TPPrice,
			&signal.Confidence,
			&signal.Reasoning,
			&signal.Status,
			&signal.ReviewResult,
			&signal.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan signal: %w", err)
		}
		signals = append(signals, signal)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating signals: %w", err)
	}

	return signals, nil
}

// UpdateStatus updates the status of a signal
func (r *SignalRepositoryImpl) UpdateStatus(ctx context.Context, id uuid.UUID, status string) error {
	query := `
		UPDATE signals
		SET status = $1
		WHERE id = $2
	`

	_, err := r.db.Exec(ctx, query, status, id)
	if err != nil {
		return fmt.Errorf("failed to update signal status: %w", err)
	}

	return nil
}

// UpdateReviewStatus updates the review result and PnL of a signal
// Returns error if update failed
func (r *SignalRepositoryImpl) UpdateReviewStatus(ctx context.Context, id uuid.UUID, result string, pnl *float64) error {
	// Optimistic locking: only update if not already finalized
	query := `
		UPDATE signals
		SET review_result = $1, review_pnl = $2
		WHERE id = $3 AND (review_result IS NULL OR review_result LIKE 'FLOATING%')
	`

	cmdTag, err := r.db.Exec(ctx, query, result, pnl, id)
	if err != nil {
		return fmt.Errorf("failed to update signal review status: %w", err)
	}

	// If no rows updated, it means it was already finalized or not found
	if cmdTag.RowsAffected() == 0 {
		return fmt.Errorf("signal already reviewed")
	}

	return nil
}

// GetPendingSignals retrieves signals that are pending review (older than specified minutes)
func (r *SignalRepositoryImpl) GetPendingSignals(ctx context.Context, olderThanMinutes int) ([]*domain.Signal, error) {
	query := `
		SELECT id, symbol, type, entry_price, sl_price, tp_price,
		       confidence, reasoning, status, review_result, created_at
		FROM signals
		WHERE status = 'PENDING'
		  AND (review_result IS NULL OR review_result LIKE 'FLOATING%')
		  AND created_at < NOW() - INTERVAL '1 minute' * $1
		ORDER BY created_at ASC
	`

	rows, err := r.db.Query(ctx, query, olderThanMinutes)
	if err != nil {
		return nil, fmt.Errorf("failed to query pending signals: %w", err)
	}
	defer rows.Close()

	var signals []*domain.Signal
	for rows.Next() {
		signal := &domain.Signal{}
		err := rows.Scan(
			&signal.ID,
			&signal.Symbol,
			&signal.Type,
			&signal.EntryPrice,
			&signal.SLPrice,
			&signal.TPPrice,
			&signal.Confidence,
			&signal.Reasoning,
			&signal.Status,
			&signal.ReviewResult,
			&signal.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan signal: %w", err)
		}
		signals = append(signals, signal)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating signals: %w", err)
	}

	return signals, nil
}
