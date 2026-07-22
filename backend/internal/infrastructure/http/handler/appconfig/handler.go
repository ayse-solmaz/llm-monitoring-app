package appconfig

import (
	"net/http"

	"github.com/masterfabric-go/masterfabric/internal/shared/response"
)

type modelInfo struct {
	ID                string `json:"id"`
	Size              string `json:"size"`
	RecommendedDevice string `json:"recommended_device"`
}

var supportedModels = []modelInfo{
	{ID: "gemma-2-2b-it-q4f16_1-MLC", Size: "2B", RecommendedDevice: "desktop"},
	{ID: "gemma-2-2b-it-q4f32_1-MLC", Size: "2B", RecommendedDevice: "desktop"},
	{ID: "gemma3-1b-it-q4f16_1-MLC", Size: "1B", RecommendedDevice: "desktop"},
	{ID: "gemma-2-9b-it-q4f16_1-MLC", Size: "9B", RecommendedDevice: "desktop-gpu"},
}

type Handler struct {
	version string
}

func NewHandler(version string) *Handler {
	return &Handler{version: version}
}

func (h *Handler) GetConfig(w http.ResponseWriter, _ *http.Request) {
	response.EnvelopeOK(w, map[string]any{
		"version": h.version,
		"features": map[string]bool{
			"auth":        true,
			"llm_persist": true,
		},
		"scoring": map[string]any{
			"weights": map[string]float64{
				"latency": 0.4,
				"length":  0.3,
				"format":  0.3,
			},
			"thresholds": map[string]int{
				"accept": 70,
				"review": 40,
			},
		},
	})
}

func (h *Handler) GetModels(w http.ResponseWriter, _ *http.Request) {
	response.EnvelopeOK(w, map[string]any{"models": supportedModels})
}
