package database

import (
	"fmt"
	"strings"

	"github.com/aysnu/llm-monitoring-app/backend/internal/models"
	"github.com/glebarez/sqlite"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func Connect(databaseURL string) (*gorm.DB, error) {
	var (
		db  *gorm.DB
		err error
	)

	if strings.HasPrefix(databaseURL, "postgres") {
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

	if err := db.AutoMigrate(
		&models.User{},
		&models.RefreshToken{},
		&models.Session{},
		&models.Message{},
		&models.Score{},
	); err != nil {
		return nil, fmt.Errorf("migrate database: %w", err)
	}

	return db, nil
}
