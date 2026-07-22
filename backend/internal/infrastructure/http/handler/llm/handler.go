package llm

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/masterfabric-go/masterfabric/internal/shared/middleware"
	"github.com/masterfabric-go/masterfabric/internal/shared/response"
)

const (
	maxContentLen    = 65536
	maxDeviceInfoLen = 512
	maxModelIDLen    = 128

	decisionAccept = "accept"
	decisionReview = "review"
	decisionReject = "reject"
)

type Handler struct {
	db *pgxpool.Pool
}

func NewHandler(db *pgxpool.Pool) *Handler {
	return &Handler{db: db}
}

type createSessionRequest struct {
	ModelID     string `json:"model_id"`
	DeviceInfo  string `json:"device_info"`
	ModelLoadMs *int64 `json:"model_load_ms"`
}

type createMessageRequest struct {
	Role             string  `json:"role"`
	Content          string  `json:"content"`
	TTFTMs           int     `json:"ttft_ms"`
	TokensPrompt     int     `json:"tokens_prompt"`
	TokensCompletion int     `json:"tokens_completion"`
	TokensPerSec     float64 `json:"tokens_per_sec"`
	TotalMs          int     `json:"total_ms"`
}

type createScoreRequest struct {
	MessageID    uuid.UUID `json:"message_id"`
	LatencyScore int       `json:"latency_score"`
	LengthScore  int       `json:"length_score"`
	FormatScore  int       `json:"format_score"`
	Composite    int       `json:"composite"`
	Decision     string    `json:"decision"`
}

type sessionRow struct {
	ID          uuid.UUID
	UserID      uuid.UUID
	ModelID     string
	DeviceInfo  string
	ModelLoadMs *int64
	CreatedAt   time.Time
}

type messageRow struct {
	ID               uuid.UUID
	SessionID        uuid.UUID
	Role             string
	Content          string
	TTFTMs           int
	TokensPrompt     int
	TokensCompletion int
	TokensPerSec     float64
	TotalMs          int
	CreatedAt        time.Time
}

type scoreRow struct {
	ID           uuid.UUID
	MessageID    uuid.UUID
	LatencyScore int
	LengthScore  int
	FormatScore  int
	Composite    int
	Decision     string
	CreatedAt    time.Time
}

func (h *Handler) CreateSession(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	var req createSessionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}
	if req.ModelID == "" {
		response.EnvelopeBadRequest(w, "model_id is required")
		return
	}
	if len(req.ModelID) > maxModelIDLen {
		response.EnvelopeBadRequest(w, "model_id must be at most 128 characters")
		return
	}
	if len(req.DeviceInfo) > maxDeviceInfoLen {
		response.EnvelopeBadRequest(w, "device_info must be at most 512 characters")
		return
	}
	if req.ModelLoadMs != nil && *req.ModelLoadMs < 0 {
		response.EnvelopeBadRequest(w, "model_load_ms must be non-negative")
		return
	}

	var s sessionRow
	err := h.db.QueryRow(r.Context(), `
		INSERT INTO sessions (id, user_id, model_id, device_info, model_load_ms)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, user_id, model_id, device_info, model_load_ms, created_at
	`, uuid.New(), userID, req.ModelID, req.DeviceInfo, req.ModelLoadMs).Scan(
		&s.ID, &s.UserID, &s.ModelID, &s.DeviceInfo, &s.ModelLoadMs, &s.CreatedAt,
	)
	if err != nil {
		response.EnvelopeInternal(w, "failed to create session")
		return
	}

	response.EnvelopeCreated(w, publicSession(s))
}

func (h *Handler) ListSessions(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	page := parseIntQuery(r, "page", 1)
	limit := parseIntQuery(r, "limit", 20)
	if page < 1 {
		page = 1
	}
	if limit < 1 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}

	var total int64
	if err := h.db.QueryRow(r.Context(), `
		SELECT COUNT(*) FROM sessions WHERE user_id = $1
	`, userID).Scan(&total); err != nil {
		response.EnvelopeInternal(w, "failed to count sessions")
		return
	}

	offset := (page - 1) * limit
	rows, err := h.db.Query(r.Context(), `
		SELECT id, user_id, model_id, device_info, model_load_ms, created_at
		FROM sessions
		WHERE user_id = $1
		ORDER BY created_at DESC
		LIMIT $2 OFFSET $3
	`, userID, limit, offset)
	if err != nil {
		response.EnvelopeInternal(w, "failed to list sessions")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	for rows.Next() {
		var s sessionRow
		if err := rows.Scan(&s.ID, &s.UserID, &s.ModelID, &s.DeviceInfo, &s.ModelLoadMs, &s.CreatedAt); err != nil {
			response.EnvelopeInternal(w, "failed to list sessions")
			return
		}
		items = append(items, publicSession(s))
	}
	if err := rows.Err(); err != nil {
		response.EnvelopeInternal(w, "failed to list sessions")
		return
	}

	response.EnvelopeOK(w, map[string]any{
		"sessions": items,
		"page":     page,
		"limit":    limit,
		"total":    total,
	})
}

func (h *Handler) GetSession(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	sessionID, ok := parseUUIDParam(w, r, "id")
	if !ok {
		return
	}

	var s sessionRow
	err := h.db.QueryRow(r.Context(), `
		SELECT id, user_id, model_id, device_info, model_load_ms, created_at
		FROM sessions
		WHERE id = $1 AND user_id = $2
	`, sessionID, userID).Scan(&s.ID, &s.UserID, &s.ModelID, &s.DeviceInfo, &s.ModelLoadMs, &s.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			response.EnvelopeNotFound(w, "session not found")
			return
		}
		response.EnvelopeInternal(w, "failed to load session")
		return
	}

	msgRows, err := h.db.Query(r.Context(), `
		SELECT
			m.id, m.session_id, m.role, m.content, m.ttft_ms, m.tokens_prompt,
			m.tokens_completion, m.tokens_per_sec, m.total_ms, m.created_at,
			sc.id, sc.message_id, sc.latency_score, sc.length_score, sc.format_score,
			sc.composite, sc.decision, sc.created_at
		FROM messages m
		LEFT JOIN scores sc ON sc.message_id = m.id
		WHERE m.session_id = $1
		ORDER BY m.created_at ASC
	`, sessionID)
	if err != nil {
		response.EnvelopeInternal(w, "failed to load session")
		return
	}
	defer msgRows.Close()

	messages := make([]map[string]any, 0)
	for msgRows.Next() {
		var m messageRow
		var scoreID *uuid.UUID
		var scoreMessageID *uuid.UUID
		var latencyScore, lengthScore, formatScore, composite *int
		var decision *string
		var scoreCreatedAt *time.Time

		if err := msgRows.Scan(
			&m.ID, &m.SessionID, &m.Role, &m.Content, &m.TTFTMs, &m.TokensPrompt,
			&m.TokensCompletion, &m.TokensPerSec, &m.TotalMs, &m.CreatedAt,
			&scoreID, &scoreMessageID, &latencyScore, &lengthScore, &formatScore,
			&composite, &decision, &scoreCreatedAt,
		); err != nil {
			response.EnvelopeInternal(w, "failed to load session")
			return
		}

		var score *scoreRow
		if scoreID != nil && scoreMessageID != nil && latencyScore != nil && lengthScore != nil &&
			formatScore != nil && composite != nil && decision != nil && scoreCreatedAt != nil {
			score = &scoreRow{
				ID:           *scoreID,
				MessageID:    *scoreMessageID,
				LatencyScore: *latencyScore,
				LengthScore:  *lengthScore,
				FormatScore:  *formatScore,
				Composite:    *composite,
				Decision:     *decision,
				CreatedAt:    *scoreCreatedAt,
			}
		}
		messages = append(messages, publicMessage(m, score))
	}
	if err := msgRows.Err(); err != nil {
		response.EnvelopeInternal(w, "failed to load session")
		return
	}

	out := publicSession(s)
	out["messages"] = messages
	response.EnvelopeOK(w, out)
}

func (h *Handler) DeleteSession(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	sessionID, ok := parseUUIDParam(w, r, "id")
	if !ok {
		return
	}

	tag, err := h.db.Exec(r.Context(), `
		DELETE FROM sessions WHERE id = $1 AND user_id = $2
	`, sessionID, userID)
	if err != nil {
		response.EnvelopeInternal(w, "failed to delete session")
		return
	}
	if tag.RowsAffected() == 0 {
		response.EnvelopeNotFound(w, "session not found")
		return
	}

	response.EnvelopeOK(w, map[string]bool{"deleted": true})
}

func (h *Handler) CreateMessage(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	sessionID, ok := parseUUIDParam(w, r, "id")
	if !ok {
		return
	}

	if !h.loadOwnedSession(w, r, userID, sessionID) {
		return
	}

	var req createMessageRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}
	if req.Role != "user" && req.Role != "assistant" {
		response.EnvelopeBadRequest(w, "role must be user or assistant")
		return
	}
	if req.Content == "" {
		response.EnvelopeBadRequest(w, "content is required")
		return
	}
	if len(req.Content) > maxContentLen {
		response.EnvelopeBadRequest(w, "content must be at most 65536 characters")
		return
	}
	if req.TTFTMs < 0 {
		response.EnvelopeBadRequest(w, "ttft_ms must be non-negative")
		return
	}
	if req.TokensPrompt < 0 {
		response.EnvelopeBadRequest(w, "tokens_prompt must be non-negative")
		return
	}
	if req.TokensCompletion < 0 {
		response.EnvelopeBadRequest(w, "tokens_completion must be non-negative")
		return
	}
	if req.TokensPerSec < 0 {
		response.EnvelopeBadRequest(w, "tokens_per_sec must be non-negative")
		return
	}
	if req.TotalMs < 0 {
		response.EnvelopeBadRequest(w, "total_ms must be non-negative")
		return
	}

	var m messageRow
	err := h.db.QueryRow(r.Context(), `
		INSERT INTO messages (
			id, session_id, role, content, ttft_ms, tokens_prompt,
			tokens_completion, tokens_per_sec, total_ms
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id, session_id, role, content, ttft_ms, tokens_prompt,
		          tokens_completion, tokens_per_sec, total_ms, created_at
	`, uuid.New(), sessionID, req.Role, req.Content, req.TTFTMs, req.TokensPrompt,
		req.TokensCompletion, req.TokensPerSec, req.TotalMs).Scan(
		&m.ID, &m.SessionID, &m.Role, &m.Content, &m.TTFTMs, &m.TokensPrompt,
		&m.TokensCompletion, &m.TokensPerSec, &m.TotalMs, &m.CreatedAt,
	)
	if err != nil {
		response.EnvelopeInternal(w, "failed to create message")
		return
	}

	response.EnvelopeCreated(w, publicMessage(m, nil))
}

func (h *Handler) CreateScore(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	sessionID, ok := parseUUIDParam(w, r, "id")
	if !ok {
		return
	}

	if !h.loadOwnedSession(w, r, userID, sessionID) {
		return
	}

	var req createScoreRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}
	if req.MessageID == uuid.Nil {
		response.EnvelopeBadRequest(w, "message_id is required")
		return
	}
	if !validScoreValue(req.LatencyScore) || !validScoreValue(req.LengthScore) ||
		!validScoreValue(req.FormatScore) || !validScoreValue(req.Composite) {
		response.EnvelopeBadRequest(w, "scores must be between 0 and 100")
		return
	}
	if !validDecision(req.Decision) {
		response.EnvelopeBadRequest(w, "decision must be accept, review, or reject")
		return
	}

	var messageID uuid.UUID
	err := h.db.QueryRow(r.Context(), `
		SELECT id FROM messages WHERE id = $1 AND session_id = $2
	`, req.MessageID, sessionID).Scan(&messageID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			response.EnvelopeNotFound(w, "message not found in session")
			return
		}
		response.EnvelopeInternal(w, "failed to lookup message")
		return
	}

	var existingID uuid.UUID
	err = h.db.QueryRow(r.Context(), `
		SELECT id FROM scores WHERE message_id = $1
	`, req.MessageID).Scan(&existingID)
	if err == nil {
		response.EnvelopeConflict(w, "score already exists for message")
		return
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		response.EnvelopeInternal(w, "failed to lookup score")
		return
	}

	var sc scoreRow
	err = h.db.QueryRow(r.Context(), `
		INSERT INTO scores (
			id, message_id, latency_score, length_score, format_score, composite, decision
		) VALUES ($1, $2, $3, $4, $5, $6, $7)
		RETURNING id, message_id, latency_score, length_score, format_score, composite, decision, created_at
	`, uuid.New(), req.MessageID, req.LatencyScore, req.LengthScore, req.FormatScore,
		req.Composite, req.Decision).Scan(
		&sc.ID, &sc.MessageID, &sc.LatencyScore, &sc.LengthScore, &sc.FormatScore,
		&sc.Composite, &sc.Decision, &sc.CreatedAt,
	)
	if err != nil {
		response.EnvelopeInternal(w, "failed to create score")
		return
	}

	response.EnvelopeCreated(w, publicScore(sc))
}

func (h *Handler) MetricsSummary(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	var avgTTFT, avgTokensPerSec *float64
	var totalTokens, sessionCount int64
	err := h.db.QueryRow(r.Context(), `
		SELECT
			AVG(m.ttft_ms) AS avg_ttft,
			AVG(m.tokens_per_sec) AS avg_tokens_per_sec,
			COALESCE(SUM(m.tokens_prompt + m.tokens_completion), 0) AS total_tokens,
			COUNT(DISTINCT s.id) AS session_count
		FROM sessions s
		LEFT JOIN messages m ON m.session_id = s.id AND m.role = 'assistant'
		WHERE s.user_id = $1
	`, userID).Scan(&avgTTFT, &avgTokensPerSec, &totalTokens, &sessionCount)
	if err != nil {
		response.EnvelopeInternal(w, "failed to compute metrics summary")
		return
	}

	response.EnvelopeOK(w, map[string]any{
		"avg_ttft_ms":        roundFloat(avgTTFT),
		"avg_tokens_per_sec": roundFloat(avgTokensPerSec),
		"total_tokens":       totalTokens,
		"session_count":      sessionCount,
	})
}

func (h *Handler) ScoresSummary(w http.ResponseWriter, r *http.Request) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return
	}

	var avgComposite *float64
	if err := h.db.QueryRow(r.Context(), `
		SELECT AVG(sc.composite) AS avg_composite
		FROM scores sc
		INNER JOIN messages m ON m.id = sc.message_id
		INNER JOIN sessions s ON s.id = m.session_id
		WHERE s.user_id = $1
	`, userID).Scan(&avgComposite); err != nil {
		response.EnvelopeInternal(w, "failed to compute scores summary")
		return
	}

	rows, err := h.db.Query(r.Context(), `
		SELECT sc.decision, COUNT(*) AS count
		FROM scores sc
		INNER JOIN messages m ON m.id = sc.message_id
		INNER JOIN sessions s ON s.id = m.session_id
		WHERE s.user_id = $1
		GROUP BY sc.decision
	`, userID)
	if err != nil {
		response.EnvelopeInternal(w, "failed to compute decision counts")
		return
	}
	defer rows.Close()

	byDecision := map[string]int64{
		decisionAccept: 0,
		decisionReview: 0,
		decisionReject: 0,
	}
	for rows.Next() {
		var decision string
		var count int64
		if err := rows.Scan(&decision, &count); err != nil {
			response.EnvelopeInternal(w, "failed to compute decision counts")
			return
		}
		byDecision[decision] = count
	}
	if err := rows.Err(); err != nil {
		response.EnvelopeInternal(w, "failed to compute decision counts")
		return
	}

	response.EnvelopeOK(w, map[string]any{
		"avg_composite": roundFloat(avgComposite),
		"by_decision":   byDecision,
	})
}

func (h *Handler) loadOwnedSession(w http.ResponseWriter, r *http.Request, userID, sessionID uuid.UUID) bool {
	var id uuid.UUID
	err := h.db.QueryRow(r.Context(), `
		SELECT id FROM sessions WHERE id = $1 AND user_id = $2
	`, sessionID, userID).Scan(&id)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			response.EnvelopeNotFound(w, "session not found")
			return false
		}
		response.EnvelopeInternal(w, "failed to lookup session")
		return false
	}
	return true
}

func publicSession(s sessionRow) map[string]any {
	return map[string]any{
		"id":            s.ID,
		"user_id":       s.UserID,
		"model_id":      s.ModelID,
		"device_info":   s.DeviceInfo,
		"model_load_ms": s.ModelLoadMs,
		"created_at":    s.CreatedAt,
	}
}

func publicMessage(m messageRow, score *scoreRow) map[string]any {
	out := map[string]any{
		"id":                m.ID,
		"session_id":        m.SessionID,
		"role":              m.Role,
		"content":           m.Content,
		"ttft_ms":           m.TTFTMs,
		"tokens_prompt":     m.TokensPrompt,
		"tokens_completion": m.TokensCompletion,
		"tokens_per_sec":    m.TokensPerSec,
		"total_ms":          m.TotalMs,
		"created_at":        m.CreatedAt,
	}
	if score != nil {
		out["score"] = publicScore(*score)
	}
	return out
}

func publicScore(s scoreRow) map[string]any {
	return map[string]any{
		"id":            s.ID,
		"message_id":    s.MessageID,
		"latency_score": s.LatencyScore,
		"length_score":  s.LengthScore,
		"format_score":  s.FormatScore,
		"composite":     s.Composite,
		"decision":      s.Decision,
		"created_at":    s.CreatedAt,
	}
}

func parseIntQuery(r *http.Request, key string, defaultVal int) int {
	raw := r.URL.Query().Get(key)
	if raw == "" {
		return defaultVal
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return defaultVal
	}
	return n
}

func parseUUIDParam(w http.ResponseWriter, r *http.Request, key string) (uuid.UUID, bool) {
	raw := chi.URLParam(r, key)
	id, err := uuid.Parse(raw)
	if err != nil {
		response.EnvelopeBadRequest(w, fmt.Sprintf("invalid %s", key))
		return uuid.Nil, false
	}
	return id, true
}

func validScoreValue(n int) bool {
	return n >= 0 && n <= 100
}

func validDecision(decision string) bool {
	switch decision {
	case decisionAccept, decisionReview, decisionReject:
		return true
	default:
		return false
	}
}

func roundFloat(v *float64) *float64 {
	if v == nil {
		return nil
	}
	rounded := math.Round(*v*100) / 100
	return &rounded
}
