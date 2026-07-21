package database

import (
	"fmt"
	"strings"
	"time"

	"github.com/aysnu/llm-monitoring-app/backend/internal/models"
	"github.com/glebarez/sqlite"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func Connect(databaseURL string) (*gorm.DB, error) {
	var (
		db      *gorm.DB
		err     error
		isPostgres bool
	)

	if strings.HasPrefix(databaseURL, "postgres") {
		isPostgres = true
		db, err = gorm.Open(postgres.Open(databaseURL), &gorm.Config{})
	} else {
		path := databaseURL
		if path == "" {
			path = "dev.db"
		}
		db, err = gorm.Open(sqlite.Open(path), &gorm.Config{})
	}

	if err != nil {
		return nil, fmt.Errorf("connect database: %w", err)
	}

	if isPostgres {
		sqlDB, err := db.DB()
		if err != nil {
			return nil, fmt.Errorf("get sql db: %w", err)
		}
		sqlDB.SetMaxOpenConns(25)
		sqlDB.SetMaxIdleConns(10)
		sqlDB.SetConnMaxLifetime(30 * time.Minute)
		sqlDB.SetConnMaxIdleTime(5 * time.Minute)
	}

	if err := db.AutoMigrate(
		&models.User{},
		&models.RefreshToken{},
		&models.Session{},
		&models.Message{},
		&models.Score{},
	); err != nil {
		return nil, fmt.Errorf("migrate database: %w", err)
	}

	if err := ensureIndexes(db); err != nil {
		return nil, err
	}

	return db, nil
}

func ensureIndexes(db *gorm.DB) error {
	stmts := []string{
		`CREATE INDEX IF NOT EXISTS idx_messages_session_role ON messages(session_id, role)`,
		`CREATE INDEX IF NOT EXISTS idx_sessions_user_created ON sessions(user_id, created_at DESC)`,
		`CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_revoked ON refresh_tokens(user_id, revoked)`,
	}
	for _, stmt := range stmts {
		if err := db.Exec(stmt).Error; err != nil {
			return fmt.Errorf("ensure index: %w", err)
		}
	}
	return nil
}
