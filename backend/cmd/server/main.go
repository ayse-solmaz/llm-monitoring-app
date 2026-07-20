package main

import (
	"log"

	"github.com/aysnu/llm-monitoring-app/backend/internal/config"
	"github.com/aysnu/llm-monitoring-app/backend/internal/database"
	"github.com/aysnu/llm-monitoring-app/backend/internal/router"
	"github.com/joho/godotenv"
)

func main() {
	_ = godotenv.Load()

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	db, err := database.Connect(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("database: %v", err)
	}

	r := router.New(cfg, db)
	if err := r.Run(":" + cfg.Port); err != nil {
		log.Fatalf("server: %v", err)
	}
}
