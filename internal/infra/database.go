package infra

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// NewDatabase creates a new database connection pool with optimized settings
func NewDatabase(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	if databaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}

	log.Println("Connecting to PostgreSQL database...")

	// Parse configuration
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse database URL: %w", err)
	}

	// Optimize pool settings
	// Limit max connections to prevent overwhelming the database (helpful for limited RAM)
	config.MaxConns = 10
	// Set minimum connections to keep some ready
	config.MinConns = 2
	// Set max connection lifetime to recycle connections occasionally
	config.MaxConnLifetime = time.Hour
	// Set max idle time to close unused connections
	config.MaxConnIdleTime = 30 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("failed to create connection pool: %w", err)
	}

	// Verify connection
	if err := pool.Ping(ctx); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	log.Println("[OK] Database connected successfully")
	return pool, nil
}
