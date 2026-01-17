package repository

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"neurotrade/internal/domain"
)

// PositionRepositoryImpl implements the PositionRepository interface
type PositionRepositoryImpl struct {
	db *pgxpool.Pool
}

// NewPositionRepository creates a new PositionRepository
func NewPositionRepository(db *pgxpool.Pool) domain.PositionRepository {
	return &PositionRepositoryImpl{db: db}
}

// Save creates a new position
func (r *PositionRepositoryImpl) Save(ctx context.Context, position *domain.Position) error {
	query := `
		INSERT INTO positions (
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
		return fmt.Errorf("failed to save position: %w", err)
	}

	return nil
}

// GetByUserID retrieves all positions for a user
func (r *PositionRepositoryImpl) GetByUserID(ctx context.Context, userID uuid.UUID) ([]*domain.Position, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, leverage, exit_price, pnl, status,
		       created_at, closed_at
		FROM positions
		WHERE user_id = $1
		ORDER BY created_at DESC
	`

	rows, err := r.db.Query(ctx, query, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to query positions by user ID: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		position := &domain.Position{}
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
func (r *PositionRepositoryImpl) GetOpenPositions(ctx context.Context) ([]*domain.Position, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, leverage, exit_price, pnl, status,
		       created_at, closed_at
		FROM positions
		WHERE status = 'OPEN'
		ORDER BY created_at ASC
	`

	rows, err := r.db.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to query open positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		position := &domain.Position{}
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
func (r *PositionRepositoryImpl) Update(ctx context.Context, position *domain.Position) error {
	query := `
		UPDATE positions
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
		return fmt.Errorf("failed to update position: %w", err)
	}

	return nil
}

// GetByID retrieves a position by ID
func (r *PositionRepositoryImpl) GetByID(ctx context.Context, id uuid.UUID) (*domain.Position, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, leverage, exit_price, pnl, status,
		       created_at, closed_at
		FROM positions
		WHERE id = $1
	`

	position := &domain.Position{}
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
func (r *PositionRepositoryImpl) GetTodayRealizedPnL(ctx context.Context, userID uuid.UUID, startOfDay time.Time) (float64, error) {
	query := `
		SELECT COALESCE(SUM(pnl), 0) 
		FROM positions 
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

// GetPnLBySignalIDs retrieves metrics for a list of signal IDs
func (r *PositionRepositoryImpl) GetPnLBySignalIDs(ctx context.Context, signalIDs []uuid.UUID) (map[uuid.UUID]domain.MetricResult, error) {
	if len(signalIDs) == 0 {
		return make(map[uuid.UUID]domain.MetricResult), nil
	}

	// Convert UUIDs to strings for array query
	idStrings := make([]string, len(signalIDs))
	for i, id := range signalIDs {
		idStrings[i] = id.String()
	}

	query := `
		SELECT signal_id::text, COALESCE(pnl, 0), entry_price, size, leverage
		FROM positions
		WHERE signal_id = ANY($1::uuid[])
	`

	rows, err := r.db.Query(ctx, query, idStrings)
	if err != nil {
		return nil, fmt.Errorf("failed to query PnL for signals: %w", err)
	}
	defer rows.Close()

	metricsMap := make(map[uuid.UUID]domain.MetricResult)
	for rows.Next() {
		var sigIDStr string
		var pnl, entryPrice, size, leverage float64
		if err := rows.Scan(&sigIDStr, &pnl, &entryPrice, &size, &leverage); err != nil {
			continue // Skip bad rows
		}

		sigID, err := uuid.Parse(sigIDStr)
		if err != nil {
			continue
		}

		// Calculate Percent
		// Initial Margin = (Size * Entry) / Leverage
		// PnL % = (PnL / Initial Margin) * 100

		var percent float64
		if leverage < 1 {
			leverage = 1
		}
		positionValue := size * entryPrice
		initialMargin := positionValue / leverage

		if initialMargin > 0 {
			percent = (pnl / initialMargin) * 100
		}

		metricsMap[sigID] = domain.MetricResult{
			PnL:        pnl,
			PnLPercent: percent,
		}
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating PnL rows: %w", err)
	}

	return metricsMap, nil
}

// GetClosedPositionsHistory retrieves closed positions for chart data
func (r *PositionRepositoryImpl) GetClosedPositionsHistory(ctx context.Context, userID uuid.UUID, limit int) ([]domain.PnLHistoryEntry, error) {
	query := `
		SELECT closed_at, COALESCE(pnl, 0)
		FROM positions
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
func (r *PositionRepositoryImpl) GetClosedPositionsHistorySince(ctx context.Context, userID uuid.UUID, since time.Time, limit int) ([]domain.PnLHistoryEntry, error) {
	query := `
		SELECT closed_at, COALESCE(pnl, 0)
		FROM positions
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
func (r *PositionRepositoryImpl) GetClosedPositions(ctx context.Context, userID uuid.UUID, limit int) ([]*domain.Position, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, leverage, exit_price, pnl, pnl_percent, status, closed_by,
		       created_at, closed_at
		FROM positions
		WHERE user_id = $1 AND status IN ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
		ORDER BY closed_at DESC
		LIMIT $2
	`

	rows, err := r.db.Query(ctx, query, userID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query closed positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		var p domain.Position
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

// GetActivePositions retrieves all active positions (OPEN or PENDING_APPROVAL)
// This is used for deduplication to prevent duplicate orders
func (r *PositionRepositoryImpl) GetActivePositions(ctx context.Context) ([]*domain.Position, error) {
	query := `
		SELECT id, user_id, signal_id, symbol, side, entry_price,
		       sl_price, tp_price, size, leverage, exit_price, pnl, status,
		       created_at, closed_at
		FROM positions
		WHERE status IN ('OPEN', 'PENDING_APPROVAL')
		ORDER BY created_at ASC
	`

	rows, err := r.db.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to query active positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		position := &domain.Position{}
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
