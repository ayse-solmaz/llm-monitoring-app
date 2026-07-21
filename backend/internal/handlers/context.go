package handlers

import (
	"github.com/aysnu/llm-monitoring-app/backend/internal/middleware"
	"github.com/aysnu/llm-monitoring-app/backend/internal/response"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

func withCtx(c *gin.Context, db *gorm.DB) *gorm.DB {
	return db.WithContext(c.Request.Context())
}

func currentUserID(c *gin.Context) (uuid.UUID, bool) {
	rawID, exists := c.Get(middleware.UserIDKey)
	if !exists {
		response.Unauthorized(c, "missing user context")
		return uuid.Nil, false
	}

	userID, ok := rawID.(uuid.UUID)
	if !ok {
		response.Unauthorized(c, "invalid user context")
		return uuid.Nil, false
	}

	return userID, true
}

func parseUUIDParam(c *gin.Context, name string) (uuid.UUID, bool) {
	raw := c.Param(name)
	id, err := uuid.Parse(raw)
	if err != nil {
		response.BadRequest(c, "invalid "+name)
		return uuid.Nil, false
	}
	return id, true
}
