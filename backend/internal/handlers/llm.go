package handlers

import (
	"errors"
	"fmt"
	"math"

	"github.com/aysnu/llm-monitoring-app/backend/internal/models"
	"github.com/aysnu/llm-monitoring-app/backend/internal/response"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

type LLMHandler struct {
	db *gorm.DB
}

func NewLLMHandler(db *gorm.DB) *LLMHandler {
	return &LLMHandler{db: db}
}

type createSessionRequest struct {
	ModelID     string `json:"model_id"`
	DeviceInfo  string `json:"device_info"`
	ModelLoadMs *int64 `json:"model_load_ms"`
}

type createMessageRequest struct {
	Role               string  `json:"role"`
	Content            string  `json:"content"`
	TTFTMs             int     `json:"ttft_ms"`
	TokensPrompt       int     `json:"tokens_prompt"`
	TokensCompletion   int     `json:"tokens_completion"`
	TokensPerSec       float64 `json:"tokens_per_sec"`
	TotalMs            int     `json:"total_ms"`
}

type createScoreRequest struct {
	MessageID    uuid.UUID `json:"message_id"`
	LatencyScore int       `json:"latency_score"`
	LengthScore  int       `json:"length_score"`
	FormatScore  int       `json:"format_score"`
	Composite    int       `json:"composite"`
	Decision     string    `json:"decision"`
}

func (h *LLMHandler) CreateSession(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	var req createSessionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}
	if req.ModelID == "" {
		response.BadRequest(c, "model_id is required")
		return
	}

	session := models.Session{
		UserID:      userID,
		ModelID:     req.ModelID,
		DeviceInfo:  req.DeviceInfo,
		ModelLoadMs: req.ModelLoadMs,
	}

	if err := h.db.Create(&session).Error; err != nil {
		response.InternalError(c, "failed to create session")
		return
	}

	response.Created(c, publicSession(session))
}

func (h *LLMHandler) ListSessions(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	page := parseIntQuery(c, "page", 1)
	limit := parseIntQuery(c, "limit", 20)
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
	if err := h.db.Model(&models.Session{}).Where("user_id = ?", userID).Count(&total).Error; err != nil {
		response.InternalError(c, "failed to count sessions")
		return
	}

	var sessions []models.Session
	offset := (page - 1) * limit
	if err := h.db.Where("user_id = ?", userID).
		Order("created_at DESC").
		Offset(offset).
		Limit(limit).
		Find(&sessions).Error; err != nil {
		response.InternalError(c, "failed to list sessions")
		return
	}

	items := make([]gin.H, 0, len(sessions))
	for _, s := range sessions {
		items = append(items, publicSession(s))
	}

	response.OK(c, gin.H{
		"sessions": items,
		"page":     page,
		"limit":    limit,
		"total":    total,
	})
}

func (h *LLMHandler) GetSession(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	sessionID, ok := parseUUIDParam(c, "id")
	if !ok {
		return
	}

	var session models.Session
	if err := h.db.Preload("Messages", func(db *gorm.DB) *gorm.DB {
		return db.Order("created_at ASC")
	}).Preload("Messages.Score").
		Where("id = ? AND user_id = ?", sessionID, userID).
		First(&session).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			response.NotFound(c, "session not found")
			return
		}
		response.InternalError(c, "failed to load session")
		return
	}

	response.OK(c, publicSessionDetail(session))
}

func (h *LLMHandler) DeleteSession(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	sessionID, ok := parseUUIDParam(c, "id")
	if !ok {
		return
	}

	result := h.db.Where("id = ? AND user_id = ?", sessionID, userID).Delete(&models.Session{})
	if result.Error != nil {
		response.InternalError(c, "failed to delete session")
		return
	}
	if result.RowsAffected == 0 {
		response.NotFound(c, "session not found")
		return
	}

	response.OK(c, gin.H{"deleted": true})
}

func (h *LLMHandler) CreateMessage(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	sessionID, ok := parseUUIDParam(c, "id")
	if !ok {
		return
	}

	if _, ok := h.loadOwnedSession(c, userID, sessionID); !ok {
		return
	}

	var req createMessageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}
	if req.Role != "user" && req.Role != "assistant" {
		response.BadRequest(c, "role must be user or assistant")
		return
	}
	if req.Content == "" {
		response.BadRequest(c, "content is required")
		return
	}

	message := models.Message{
		SessionID:        sessionID,
		Role:             req.Role,
		Content:          req.Content,
		TTFTMs:           req.TTFTMs,
		TokensPrompt:     req.TokensPrompt,
		TokensCompletion: req.TokensCompletion,
		TokensPerSec:     req.TokensPerSec,
		TotalMs:          req.TotalMs,
	}

	if err := h.db.Create(&message).Error; err != nil {
		response.InternalError(c, "failed to create message")
		return
	}

	response.Created(c, publicMessage(message))
}

func (h *LLMHandler) CreateScore(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	sessionID, ok := parseUUIDParam(c, "id")
	if !ok {
		return
	}

	if _, ok := h.loadOwnedSession(c, userID, sessionID); !ok {
		return
	}

	var req createScoreRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}
	if req.MessageID == uuid.Nil {
		response.BadRequest(c, "message_id is required")
		return
	}
	if !validScoreValue(req.LatencyScore) || !validScoreValue(req.LengthScore) ||
		!validScoreValue(req.FormatScore) || !validScoreValue(req.Composite) {
		response.BadRequest(c, "scores must be between 0 and 100")
		return
	}
	if !models.ValidDecision(req.Decision) {
		response.BadRequest(c, "decision must be accept, review, or reject")
		return
	}

	var message models.Message
	if err := h.db.Where("id = ? AND session_id = ?", req.MessageID, sessionID).
		First(&message).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			response.NotFound(c, "message not found in session")
			return
		}
		response.InternalError(c, "failed to lookup message")
		return
	}

	var existing models.Score
	if err := h.db.Where("message_id = ?", req.MessageID).First(&existing).Error; err == nil {
		response.Conflict(c, "score already exists for message")
		return
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		response.InternalError(c, "failed to lookup score")
		return
	}

	score := models.Score{
		MessageID:    req.MessageID,
		LatencyScore: req.LatencyScore,
		LengthScore:  req.LengthScore,
		FormatScore:  req.FormatScore,
		Composite:    req.Composite,
		Decision:     req.Decision,
	}

	if err := h.db.Create(&score).Error; err != nil {
		response.InternalError(c, "failed to create score")
		return
	}

	response.Created(c, publicScore(score))
}

func (h *LLMHandler) MetricsSummary(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	type row struct {
		AvgTTFT        *float64
		AvgTokensPerSec *float64
		TotalTokens    int64
		SessionCount   int64
	}

	var result row
	err := h.db.Raw(`
		SELECT
			AVG(m.ttft_ms) AS avg_ttft,
			AVG(m.tokens_per_sec) AS avg_tokens_per_sec,
			COALESCE(SUM(m.tokens_prompt + m.tokens_completion), 0) AS total_tokens,
			COUNT(DISTINCT s.id) AS session_count
		FROM sessions s
		LEFT JOIN messages m ON m.session_id = s.id AND m.role = 'assistant'
		WHERE s.user_id = ?
	`, userID).Scan(&result).Error
	if err != nil {
		response.InternalError(c, "failed to compute metrics summary")
		return
	}

	response.OK(c, gin.H{
		"avg_ttft_ms":       roundFloat(result.AvgTTFT),
		"avg_tokens_per_sec": roundFloat(result.AvgTokensPerSec),
		"total_tokens":      result.TotalTokens,
		"session_count":     result.SessionCount,
	})
}

func (h *LLMHandler) ScoresSummary(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		return
	}

	type avgRow struct {
		AvgComposite *float64
	}
	var avg avgRow
	if err := h.db.Raw(`
		SELECT AVG(sc.composite) AS avg_composite
		FROM scores sc
		INNER JOIN messages m ON m.id = sc.message_id
		INNER JOIN sessions s ON s.id = m.session_id
		WHERE s.user_id = ?
	`, userID).Scan(&avg).Error; err != nil {
		response.InternalError(c, "failed to compute scores summary")
		return
	}

	type countRow struct {
		Decision string
		Count    int64
	}
	var counts []countRow
	if err := h.db.Raw(`
		SELECT sc.decision, COUNT(*) AS count
		FROM scores sc
		INNER JOIN messages m ON m.id = sc.message_id
		INNER JOIN sessions s ON s.id = m.session_id
		WHERE s.user_id = ?
		GROUP BY sc.decision
	`, userID).Scan(&counts).Error; err != nil {
		response.InternalError(c, "failed to compute decision counts")
		return
	}

	byDecision := gin.H{
		models.DecisionAccept: int64(0),
		models.DecisionReview: int64(0),
		models.DecisionReject: int64(0),
	}
	for _, row := range counts {
		byDecision[row.Decision] = row.Count
	}

	response.OK(c, gin.H{
		"avg_composite": roundFloat(avg.AvgComposite),
		"by_decision":   byDecision,
	})
}

func (h *LLMHandler) loadOwnedSession(c *gin.Context, userID, sessionID uuid.UUID) (models.Session, bool) {
	var session models.Session
	if err := h.db.Where("id = ? AND user_id = ?", sessionID, userID).First(&session).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			response.NotFound(c, "session not found")
			return models.Session{}, false
		}
		response.InternalError(c, "failed to lookup session")
		return models.Session{}, false
	}
	return session, true
}

func publicSession(s models.Session) gin.H {
	return gin.H{
		"id":            s.ID,
		"user_id":       s.UserID,
		"model_id":      s.ModelID,
		"device_info":   s.DeviceInfo,
		"model_load_ms": s.ModelLoadMs,
		"created_at":    s.CreatedAt,
	}
}

func publicSessionDetail(s models.Session) gin.H {
	messages := make([]gin.H, 0, len(s.Messages))
	for _, m := range s.Messages {
		messages = append(messages, publicMessage(m))
	}

	out := publicSession(s)
	out["messages"] = messages
	return out
}

func publicMessage(m models.Message) gin.H {
	out := gin.H{
		"id":                  m.ID,
		"session_id":          m.SessionID,
		"role":                m.Role,
		"content":             m.Content,
		"ttft_ms":             m.TTFTMs,
		"tokens_prompt":       m.TokensPrompt,
		"tokens_completion":   m.TokensCompletion,
		"tokens_per_sec":      m.TokensPerSec,
		"total_ms":            m.TotalMs,
		"created_at":          m.CreatedAt,
	}
	if m.Score != nil {
		out["score"] = publicScore(*m.Score)
	}
	return out
}

func publicScore(s models.Score) gin.H {
	return gin.H{
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

func parseIntQuery(c *gin.Context, key string, defaultVal int) int {
	raw := c.Query(key)
	if raw == "" {
		return defaultVal
	}
	var n int
	if _, err := fmt.Sscanf(raw, "%d", &n); err != nil {
		return defaultVal
	}
	return n
}

func validScoreValue(n int) bool {
	return n >= 0 && n <= 100
}

func roundFloat(v *float64) *float64 {
	if v == nil {
		return nil
	}
	rounded := math.Round(*v*100) / 100
	return &rounded
}
