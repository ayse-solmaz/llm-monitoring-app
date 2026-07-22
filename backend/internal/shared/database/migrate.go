package database

import (
	"database/sql"
	"fmt"
	"log/slog"
	"os"

	"github.com/masterfabric-go/masterfabric/internal/shared/config"
	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/pressly/goose/v3"
)

func migrationsDir() string {
	if p := os.Getenv("MIGRATIONS_DIR"); p != "" {
		return p
	}
	if _, err := os.Stat("migrations"); err == nil {
		return "migrations"
	}
	return "internal/infrastructure/postgres/migrations"
}

// RunMigrations applies pending goose migrations.
func RunMigrations(cfg config.DatabaseConfig, log *slog.Logger) error {
	db, err := sql.Open("pgx", cfg.ConnectionString())
	if err != nil {
		return fmt.Errorf("open db for migrations: %w", err)
	}
	defer db.Close()

	if err := goose.SetDialect("postgres"); err != nil {
		return fmt.Errorf("goose dialect: %w", err)
	}

	dir := migrationsDir()
	if err := goose.Up(db, dir); err != nil {
		return fmt.Errorf("goose up (%s): %w", dir, err)
	}

	log.Info("database migrations applied", "dir", dir)
	return nil
}
