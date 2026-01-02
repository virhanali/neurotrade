package repository

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// SystemSetting represents a system configuration entry
type SystemSetting struct {
	Key         string    `json:"key"`
	Value       string    `json:"value"`
	Description string    `json:"description,omitempty"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// SystemSettingsRepository handles system settings database operations
type SystemSettingsRepository struct {
	db *pgxpool.Pool
}

// NewSystemSettingsRepository creates a new repository instance
func NewSystemSettingsRepository(db *pgxpool.Pool) *SystemSettingsRepository {
	return &SystemSettingsRepository{db: db}
}

// Get retrieves a setting by key
func (r *SystemSettingsRepository) Get(ctx context.Context, key string) (*SystemSetting, error) {
	var setting SystemSetting
	err := r.db.QueryRow(ctx, `
		SELECT key, value, COALESCE(description, ''), updated_at
		FROM system_settings
		WHERE key = $1
	`, key).Scan(&setting.Key, &setting.Value, &setting.Description, &setting.UpdatedAt)

	if err != nil {
		return nil, fmt.Errorf("setting not found: %s", key)
	}

	return &setting, nil
}

// Set updates or creates a setting
func (r *SystemSettingsRepository) Set(ctx context.Context, key, value string) error {
	_, err := r.db.Exec(ctx, `
		INSERT INTO system_settings (key, value, updated_at)
		VALUES ($1, $2, CURRENT_TIMESTAMP)
		ON CONFLICT (key) DO UPDATE SET 
			value = EXCLUDED.value,
			updated_at = CURRENT_TIMESTAMP
	`, key, value)

	if err != nil {
		return fmt.Errorf("failed to set setting %s: %w", key, err)
	}

	return nil
}

// GetTradingMode retrieves the current trading mode (SCALPER or INVESTOR)
func (r *SystemSettingsRepository) GetTradingMode(ctx context.Context) (string, error) {
	setting, err := r.Get(ctx, "trading_mode")
	if err != nil {
		// Return default if not found
		return "SCALPER", nil
	}
	return setting.Value, nil
}

// SetTradingMode updates the trading mode
func (r *SystemSettingsRepository) SetTradingMode(ctx context.Context, mode string) error {
	// Validate mode
	if mode != "SCALPER" && mode != "INVESTOR" {
		return fmt.Errorf("invalid trading mode: %s (must be SCALPER or INVESTOR)", mode)
	}
	return r.Set(ctx, "trading_mode", mode)
}

// GetAll retrieves all system settings
func (r *SystemSettingsRepository) GetAll(ctx context.Context) ([]*SystemSetting, error) {
	rows, err := r.db.Query(ctx, `
		SELECT key, value, COALESCE(description, ''), updated_at
		FROM system_settings
		ORDER BY key
	`)
	if err != nil {
		return nil, fmt.Errorf("failed to get all settings: %w", err)
	}
	defer rows.Close()

	var settings []*SystemSetting
	for rows.Next() {
		var s SystemSetting
		if err := rows.Scan(&s.Key, &s.Value, &s.Description, &s.UpdatedAt); err != nil {
			return nil, err
		}
		settings = append(settings, &s)
	}

	return settings, nil
}
