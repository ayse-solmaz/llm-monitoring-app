package handlers

import (
	"net/http"
	"strings"

	"github.com/aysnu/llm-monitoring-app/backend/internal/config"
	"github.com/aysnu/llm-monitoring-app/backend/internal/response"
	"github.com/gin-gonic/gin"
)

type CMNHandler struct {
	cfg *config.Config
}

func NewCMNHandler(cfg *config.Config) *CMNHandler {
	return &CMNHandler{cfg: cfg}
}

func (h *CMNHandler) Healthz(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func (h *CMNHandler) Version(c *gin.Context) {
	response.OK(c, gin.H{
		"version":     h.cfg.Version,
		"commit_hash": h.cfg.GitCommit,
	})
}

type ModelInfo struct {
	ID                string `json:"id"`
	Size              string `json:"size"`
	RecommendedDevice string `json:"recommended_device"`
}

var supportedModels = []ModelInfo{
	{ID: "gemma-2-2b-it-q4f16_1-MLC", Size: "2B", RecommendedDevice: "desktop"},
	{ID: "gemma-2-2b-it-q4f32_1-MLC", Size: "2B", RecommendedDevice: "desktop"},
	{ID: "gemma3-1b-it-q4f16_1-MLC", Size: "1B", RecommendedDevice: "desktop"},
	{ID: "gemma-2-9b-it-q4f16_1-MLC", Size: "9B", RecommendedDevice: "desktop-gpu"},
}

type ConfigHandler struct {
	cfg *config.Config
}

func NewConfigHandler(cfg *config.Config) *ConfigHandler {
	return &ConfigHandler{cfg: cfg}
}

func (h *ConfigHandler) GetConfig(c *gin.Context) {
	response.OK(c, gin.H{
		"version": h.cfg.Version,
		"features": gin.H{
			"auth":       true,
			"llm_persist": false,
		},
		"scoring": gin.H{
			"weights": gin.H{
				"latency": 0.4,
				"length":  0.3,
				"format":  0.3,
			},
			"thresholds": gin.H{
				"accept": 70,
				"review": 40,
			},
		},
	})
}

func (h *ConfigHandler) GetModels(c *gin.Context) {
	response.OK(c, gin.H{
		"models": supportedModels,
	})
}

func normalizeEmail(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}
