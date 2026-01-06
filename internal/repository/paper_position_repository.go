package repository

import (
	"context"
	"fmt"
	"time"

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
			sl_price, tp_price, size, leverage, status, created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
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
		position.Leverage,
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
		       sl_price, tp_price, size, leverage, exit_price, pnl, status,
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
			&position.Leverage,
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
		       sl_price, tp_price, size, leverage, exit_price, pnl, status,
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
			&position.Leverage,
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

// Update updates position status, exit price, PnL, and SL price (for trailing stop)
func (r *PaperPositionRepositoryImpl) Update(ctx context.Context, position *domain.PaperPosition) error {
	query := `
		UPDATE paper_positions
		SET exit_price = $1,
		    pnl = $2,
		    status = $3,
		    closed_at = $4,
		    sl_price = $5,
		    pnl_percent = $6,
		    closed_by = $7,
		    leverage = $8
		WHERE id = $9
	`

	_, err := r.db.Exec(ctx, query,
		position.ExitPrice,
		position.PnL,
		position.Status,
		position.ClosedAt,
		position.SLPrice,
		position.PnLPercent,
		position.ClosedBy,
		position.Leverage,
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
		       sl_price, tp_price, size, leverage, exit_price, pnl, status,
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
		&position.Leverage,
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

// GetTodayRealizedPnL retrieves the realized PnL for positions closed today (WIB)
func (r *PaperPositionRepositoryImpl) GetTodayRealizedPnL(ctx context.Context, userID uuid.UUID, startOfDay time.Time) (float64, error) {
	query := `
		SELECT COALESCE(SUM(pnl), 0) 
		FROM paper_positions 
		WHERE user_id = $1 
		AND closed_at >= $2 
		AND status IN ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
	`

	var todayPnL float64
	err := r.db.QueryRow(ctx, query, userID, startOfDay).Scan(&todayPnL)
	if err != nil {
		return 0, fmt.Errorf("failed to calculate today's PnL: %w", err)
	}

	return todayPnL, nil
}

// GetPnLBySignalIDs retrieves PnL values for a list of signal IDs
func (r *PaperPositionRepositoryImpl) GetPnLBySignalIDs(ctx context.Context, signalIDs []uuid.UUID) (map[uuid.UUID]float64, error) {
	if len(signalIDs) == 0 {
		return make(map[uuid.UUID]float64), nil
	}

	// Convert UUIDs to strings for array query
	idStrings := make([]string, len(signalIDs))
	for i, id := range signalIDs {
		idStrings[i] = id.String()
	}

	query := `
		SELECT signal_id::text, COALESCE(pnl, 0)
		FROM paper_positions
		WHERE signal_id = ANY($1::uuid[])
	`

	rows, err := r.db.Query(ctx, query, idStrings)
	if err != nil {
		return nil, fmt.Errorf("failed to query PnL for signals: %w", err)
	}
	defer rows.Close()

	pnlMap := make(map[uuid.UUID]float64)
	for rows.Next() {
		var signalIDStr string
		var pnl float64
		if err := rows.Scan(&signalIDStr, &pnl); err == nil {
			if id, err := uuid.Parse(signalIDStr); err == nil {
				pnlMap[id] = pnl
			}
		}
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating pnl rows: %w", err)
	}

	return pnlMap, nil
}

// GetClosedPositionsHistory retrieves closed positions for chart data
func (r *PaperPositionRepositoryImpl) GetClosedPositionsHistory(ctx context.Context, userID uuid.UUID, limit int) ([]domain.PnLHistoryEntry, error) {
	query := `
		SELECT closed_at, COALESCE(pnl, 0)
		FROM paper_positions
		WHERE user_id = $1 
		AND status IN ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
		AND closed_at IS NOT NULL
		ORDER BY closed_at ASC
		LIMIT $2
	`

	rows, err := r.db.Query(ctx, query, userID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query history: %w", err)
	}
	defer rows.Close()

	var history []domain.PnLHistoryEntry
	for rows.Next() {
		var entry domain.PnLHistoryEntry
		if err := rows.Scan(&entry.ClosedAt, &entry.PnL); err != nil {
			return nil, fmt.Errorf("failed to scan history entry: %w", err)
		}
		history = append(history, entry)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating history rows: %w", err)
	}

	return history, nil
}

// GetClosedPositionsHistorySince retrieves closed positions since a specific time
func (r *PaperPositionRepositoryImpl) GetClosedPositionsHistorySince(ctx context.Context, userID uuid.UUID, since time.Time, limit int) ([]domain.PnLHistoryEntry, error) {
	query := `
		SELECT closed_at, COALESCE(pnl, 0)
		FROM paper_positions
		WHERE user_id = $1 
		AND status IN ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
		AND closed_at IS NOT NULL
		AND closed_at >= $2
		ORDER BY closed_at ASC
		LIMIT $3
	`

	rows, err := r.db.Query(ctx, query, userID, since, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query history since: %w", err)
	}
	defer rows.Close()

	var history []domain.PnLHistoryEntry
	for rows.Next() {
		var entry domain.PnLHistoryEntry
		if err := rows.Scan(&entry.ClosedAt, &entry.PnL); err != nil {
			return nil, fmt.Errorf("failed to scan history entry: %w", err)
		}
		history = append(history, entry)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating history rows: %w", err)
	}

	return history, nil
}

// GetClosedPositions retrieves closed positions for a user with all details
func (r *PaperPositionRepositoryImpl) GetClosedPositions(ctx context.Context, userID uuid.UUID, limit int) ([]*domain.PaperPosition, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, leverage, exit_price, pnl, pnl_percent, status, closed_by,
		       created_at, closed_at
		FROM paper_positions
		WHERE user_id = $1 AND status IN ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
		ORDER BY closed_at DESC
		LIMIT $2
	`

	rows, err := r.db.Query(ctx, query, userID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query closed positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.PaperPosition
	for rows.Next() {
		var p domain.PaperPosition
		if err := rows.Scan(
			&p.ID, &p.UserID, &p.SignalID, &p.Symbol, &p.Side, &p.EntryPrice,
			&p.SLPrice, &p.TPPrice, &p.Size, &p.Leverage, &p.ExitPrice, &p.PnL, &p.PnLPercent, &p.Status, &p.ClosedBy,
			&p.CreatedAt, &p.ClosedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan position: %w", err)
		}
		positions = append(positions, &p)
	}

	return positions, nil
}
