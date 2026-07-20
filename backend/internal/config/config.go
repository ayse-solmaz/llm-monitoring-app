package config

import (
	"fmt"
	"os"
	"time"
)

const (
	AccessTokenTTL  = 15 * time.Minute
	RefreshTokenTTL = 7 * 24 * time.Hour
)

type Config struct {
	Port        string
	DatabaseURL string
	JWTSecret   string
	CORSOrigin  string
	Version     string
	GitCommit   string
}

func Load() (*Config, error) {
	cfg := &Config{
		Port:        getEnv("PORT", "8080"),
		DatabaseURL: os.Getenv("DATABASE_URL"),
		JWTSecret:   os.Getenv("JWT_SECRET"),
		CORSOrigin:  getEnv("CORS_ORIGIN", "http://localhost:3000"),
		Version:     getEnv("BUILD_VERSION", "0.1.0"),
		GitCommit:   getEnv("GIT_COMMIT", "dev"),
	}

	if cfg.DatabaseURL == "" {
		cfg.DatabaseURL = "dev.db"
	}
	if cfg.JWTSecret == "" {
		return nil, fmt.Errorf("JWT_SECRET is required")
	}

	return cfg, nil
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
