package llmadmin

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/masterfabric-go/masterfabric/internal/shared/middleware"
	"github.com/masterfabric-go/masterfabric/internal/shared/response"
)

const settingsRowID = 1

var knownAdapters = map[string]struct{}{
	"":               {},
	"deepkwiki":      {},
	"code-assistant": {},
}

type Handler struct {
	db *pgxpool.Pool
}

func NewHandler(db *pgxpool.Pool) *Handler {
	return &Handler{db: db}
}

type Settings struct {
	SystemPrompt     string  `json:"system_prompt"`
	Temperature      float64 `json:"temperature"`
	TopP             float64 `json:"top_p"`
	MaxTokens        int     `json:"max_tokens"`
	AdapterID        string  `json:"adapter_id"`
	DeepKwikiEnabled bool    `json:"deep_kwiki_enabled"`
	UpdatedAt        string  `json:"updated_at,omitempty"`
}

type updateRequest struct {
	SystemPrompt     string  `json:"system_prompt"`
	Temperature      float64 `json:"temperature"`
	TopP             float64 `json:"top_p"`
	MaxTokens        int     `json:"max_tokens"`
	AdapterID        string  `json:"adapter_id"`
	DeepKwikiEnabled bool    `json:"deep_kwiki_enabled"`
}

func defaultSettings() Settings {
	prompt := strings.TrimSpace(os.Getenv("LLM_DEFAULT_SYSTEM_PROMPT"))
	if prompt == "" {
		prompt = "Answer briefly and accurately. Prefer Turkish when the user writes Turkish."
	}
	return Settings{
		SystemPrompt:     prompt,
		Temperature:      0,
		TopP:             0.9,
		MaxTokens:        48,
		AdapterID:        "",
		DeepKwikiEnabled: true,
	}
}

func (h *Handler) GetSettings(w http.ResponseWriter, r *http.Request) {
	settings, err := h.loadSettings(r.Context())
	if err != nil {
		response.EnvelopeInternal(w, "failed to load llm admin settings")
		return
	}
	response.EnvelopeOK(w, settings)
}

func (h *Handler) PutSettings(w http.ResponseWriter, r *http.Request) {
	var req updateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}

	if err := validateUpdate(&req); err != nil {
		response.EnvelopeBadRequest(w, err.Error())
		return
	}

	var updatedBy *uuid.UUID
	if userID, ok := middleware.UserIDFromContext(r.Context()); ok && userID != uuid.Nil {
		updatedBy = &userID
	}

	settings, err := h.saveSettings(r.Context(), req, updatedBy)
	if err != nil {
		response.EnvelopeInternal(w, "failed to save llm admin settings")
		return
	}
	response.EnvelopeOK(w, settings)
}

func validateUpdate(req *updateRequest) error {
	req.SystemPrompt = strings.TrimSpace(req.SystemPrompt)
	if len(req.SystemPrompt) > 4096 {
		return fmt.Errorf("system_prompt too long (max 4096)")
	}
	if _, ok := knownAdapters[req.AdapterID]; !ok {
		return fmt.Errorf("unknown adapter_id %q", req.AdapterID)
	}
	if req.MaxTokens <= 0 {
		req.MaxTokens = 48
	}
	if req.MaxTokens > 512 {
		req.MaxTokens = 512
	}
	if req.Temperature < 0 {
		req.Temperature = 0
	}
	if req.Temperature > 2 {
		req.Temperature = 2
	}
	if req.TopP <= 0 || req.TopP > 1 {
		req.TopP = 0.9
	}
	return nil
}

func (h *Handler) loadSettings(ctx context.Context) (Settings, error) {
	row := h.db.QueryRow(ctx, `
		SELECT system_prompt, temperature, top_p, max_tokens, adapter_id, deep_kwiki_enabled, updated_at
		FROM llm_admin_settings
		WHERE id = $1
	`, settingsRowID)

	var s Settings
	var updatedAt time.Time
	err := row.Scan(
		&s.SystemPrompt,
		&s.Temperature,
		&s.TopP,
		&s.MaxTokens,
		&s.AdapterID,
		&s.DeepKwikiEnabled,
		&updatedAt,
	)
	if err == pgx.ErrNoRows {
		def := defaultSettings()
		if _, insErr := h.db.Exec(ctx, `
			INSERT INTO llm_admin_settings (
				id, system_prompt, temperature, top_p, max_tokens, adapter_id, deep_kwiki_enabled
			) VALUES ($1, $2, $3, $4, $5, $6, $7)
			ON CONFLICT (id) DO NOTHING
		`, settingsRowID, def.SystemPrompt, def.Temperature, def.TopP, def.MaxTokens, def.AdapterID, def.DeepKwikiEnabled); insErr != nil {
			return Settings{}, insErr
		}
		def.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
		return def, nil
	}
	if err != nil {
		return Settings{}, err
	}
	s.UpdatedAt = updatedAt.UTC().Format(time.RFC3339)
	return s, nil
}

func (h *Handler) saveSettings(ctx context.Context, req updateRequest, updatedBy *uuid.UUID) (Settings, error) {
	var s Settings
	var updatedAt time.Time
	err := h.db.QueryRow(ctx, `
		INSERT INTO llm_admin_settings (
			id, system_prompt, temperature, top_p, max_tokens, adapter_id, deep_kwiki_enabled, updated_by
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (id) DO UPDATE SET
			system_prompt = EXCLUDED.system_prompt,
			temperature = EXCLUDED.temperature,
			top_p = EXCLUDED.top_p,
			max_tokens = EXCLUDED.max_tokens,
			adapter_id = EXCLUDED.adapter_id,
			deep_kwiki_enabled = EXCLUDED.deep_kwiki_enabled,
			updated_by = EXCLUDED.updated_by,
			updated_at = NOW()
		RETURNING system_prompt, temperature, top_p, max_tokens, adapter_id, deep_kwiki_enabled, updated_at
	`, settingsRowID, req.SystemPrompt, req.Temperature, req.TopP, req.MaxTokens, req.AdapterID, req.DeepKwikiEnabled, updatedBy).Scan(
		&s.SystemPrompt,
		&s.Temperature,
		&s.TopP,
		&s.MaxTokens,
		&s.AdapterID,
		&s.DeepKwikiEnabled,
		&updatedAt,
	)
	if err != nil {
		return Settings{}, err
	}
	s.UpdatedAt = updatedAt.UTC().Format(time.RFC3339)
	return s, nil
}
