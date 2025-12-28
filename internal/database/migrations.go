package database

import (
	"context"
	"embed"
	"fmt"
	"log"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

// RunMigrations runs all database migrations on startup
func RunMigrations(db *pgxpool.Pool) error {
	ctx := context.Background()

	log.Println("Running database migrations...")

	// Create migrations tracking table if not exists
	_, err := db.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version VARCHAR(255) PRIMARY KEY,
			applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return fmt.Errorf("failed to create migrations table: %w", err)
	}

	// Read all migration files
	entries, err := migrationsFS.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("failed to read migrations directory: %w", err)
	}

	// Filter and sort .sql files
	var migrationFiles []string
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".sql") {
			migrationFiles = append(migrationFiles, entry.Name())
		}
	}
	sort.Strings(migrationFiles) // Sort to ensure order (001, 002, 003, etc.)

	log.Printf("Found %d migration file(s)", len(migrationFiles))

	// Run each migration if not already applied
	appliedCount := 0
	for _, filename := range migrationFiles {
		version := strings.TrimSuffix(filename, ".sql")

		// Check if already applied
		var exists bool
		err := db.QueryRow(ctx, `
			SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = $1)
		`, version).Scan(&exists)
		if err != nil {
			return fmt.Errorf("failed to check migration status for %s: %w", version, err)
		}

		if exists {
			log.Printf("  [SKIP] %s (already applied)", filename)
			continue
		}

		// Read migration file
		content, err := migrationsFS.ReadFile(filepath.Join("migrations", filename))
		if err != nil {
			return fmt.Errorf("failed to read migration %s: %w", filename, err)
		}

		// Execute migration
		log.Printf("  [APPLY] %s...", filename)
		_, err = db.Exec(ctx, string(content))
		if err != nil {
			return fmt.Errorf("failed to apply migration %s: %w", filename, err)
		}

		// Mark as applied
		_, err = db.Exec(ctx, `
			INSERT INTO schema_migrations (version) VALUES ($1)
		`, version)
		if err != nil {
			return fmt.Errorf("failed to mark migration %s as applied: %w", version, err)
		}

		log.Printf("  [OK] %s applied successfully", filename)
		appliedCount++
	}

	if appliedCount == 0 {
		log.Println("All migrations already applied, database is up to date")
	} else {
		log.Printf("Applied %d new migration(s) successfully", appliedCount)
	}

	return nil
}
