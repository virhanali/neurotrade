package database

import (
	"context"
	_ "embed"
	"fmt"
	"log"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/001_init_schema.sql
var migrationSQL string

// RunMigrations runs database migrations on startup
func RunMigrations(db *pgxpool.Pool) error {
	ctx := context.Background()

	log.Println("🔄 Running database migrations...")

	// Check if users table exists
	var exists bool
	err := db.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT FROM information_schema.tables 
			WHERE table_name = 'users'
		)
	`).Scan(&exists)
	if err != nil {
		return fmt.Errorf("failed to check if migrations needed: %w", err)
	}

	if exists {
		log.Println("✓ Database already migrated, skipping...")
		return nil
	}

	log.Println("📦 Database is empty, running migrations...")

	// Run migration SQL from embedded file
	_, err = db.Exec(ctx, migrationSQL)
	if err != nil {
		return fmt.Errorf("failed to run migrations: %w", err)
	}

	log.Println("✅ Database migrations completed successfully!")
	return nil
}
