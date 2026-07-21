package main

import (
	"log"
	"net/http"
	"time"

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

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      r,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server: %v", err)
	}
}
