package handlers

import (
	"errors"
	"strings"
	"time"

	"github.com/aysnu/llm-monitoring-app/backend/internal/auth"
	"github.com/aysnu/llm-monitoring-app/backend/internal/config"
	"github.com/aysnu/llm-monitoring-app/backend/internal/middleware"
	"github.com/aysnu/llm-monitoring-app/backend/internal/models"
	"github.com/aysnu/llm-monitoring-app/backend/internal/response"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

type AuthHandler struct {
	db        *gorm.DB
	jwtSecret string
}

func NewAuthHandler(db *gorm.DB, jwtSecret string) *AuthHandler {
	return &AuthHandler{db: db, jwtSecret: jwtSecret}
}

type registerRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type refreshRequest struct {
	RefreshToken string `json:"refresh_token"`
}

type logoutRequest struct {
	RefreshToken string `json:"refresh_token"`
}

type updateProfileRequest struct {
	Name string `json:"name"`
}

type changePasswordRequest struct {
	CurrentPassword string `json:"current_password"`
	NewPassword     string `json:"new_password"`
}

type tokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
}

func (h *AuthHandler) Register(c *gin.Context) {
	var req registerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}

	email := normalizeEmail(req.Email)
	if !isValidEmail(email) {
		response.BadRequest(c, "invalid email")
		return
	}
	if len(req.Password) < 8 {
		response.BadRequest(c, "password must be at least 8 characters")
		return
	}

	hash, err := auth.HashPassword(req.Password)
	if err != nil {
		response.InternalError(c, "failed to hash password")
		return
	}

	user := models.User{
		Email:        email,
		PasswordHash: hash,
		Name:         strings.TrimSpace(req.Name),
	}

	if err := h.db.Create(&user).Error; err != nil {
		if isDuplicateKeyError(err) {
			response.Conflict(c, "email already registered")
			return
		}
		response.InternalError(c, "failed to create user")
		return
	}

	response.Created(c, publicUser(user))
}

func (h *AuthHandler) Login(c *gin.Context) {
	var req loginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}

	email := normalizeEmail(req.Email)
	var user models.User
	if err := h.db.Where("email = ?", email).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			response.Unauthorized(c, "invalid email or password")
			return
		}
		response.InternalError(c, "failed to lookup user")
		return
	}

	if err := auth.CheckPassword(user.PasswordHash, req.Password); err != nil {
		response.Unauthorized(c, "invalid email or password")
		return
	}

	tokens, err := h.issueTokens(user.ID)
	if err != nil {
		response.InternalError(c, "failed to issue tokens")
		return
	}

	response.OK(c, tokens)
}

func (h *AuthHandler) Refresh(c *gin.Context) {
	var req refreshRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}
	if req.RefreshToken == "" {
		response.BadRequest(c, "refresh_token is required")
		return
	}

	tokenHash := auth.HashRefreshToken(req.RefreshToken)
	var stored models.RefreshToken
	if err := h.db.Where("token_hash = ?", tokenHash).First(&stored).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			response.Unauthorized(c, "invalid refresh token")
			return
		}
		response.InternalError(c, "failed to lookup refresh token")
		return
	}

	if stored.Revoked || time.Now().After(stored.ExpiresAt) {
		response.Unauthorized(c, "invalid refresh token")
		return
	}

	accessToken, err := auth.GenerateAccessToken(stored.UserID, h.jwtSecret)
	if err != nil {
		response.InternalError(c, "failed to generate access token")
		return
	}

	response.OK(c, gin.H{
		"access_token": accessToken,
		"expires_in":   int(config.AccessTokenTTL.Seconds()),
	})
}

func (h *AuthHandler) Logout(c *gin.Context) {
	var req logoutRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}
	if req.RefreshToken == "" {
		response.BadRequest(c, "refresh_token is required")
		return
	}

	tokenHash := auth.HashRefreshToken(req.RefreshToken)
	result := h.db.Model(&models.RefreshToken{}).
		Where("token_hash = ? AND revoked = ?", tokenHash, false).
		Update("revoked", true)
	if result.Error != nil {
		response.InternalError(c, "failed to revoke refresh token")
		return
	}
	if result.RowsAffected == 0 {
		response.NotFound(c, "refresh token not found")
		return
	}

	response.OK(c, gin.H{"message": "logged out"})
}

func (h *AuthHandler) Me(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}
	response.OK(c, publicUser(user))
}

func (h *AuthHandler) UpdateMe(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}

	var req updateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}

	name := strings.TrimSpace(req.Name)
	if name == "" {
		response.BadRequest(c, "name is required")
		return
	}

	if err := h.db.Model(&user).Update("name", name).Error; err != nil {
		response.InternalError(c, "failed to update profile")
		return
	}

	user.Name = name
	response.OK(c, publicUser(user))
}

func (h *AuthHandler) ChangePassword(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}

	var req changePasswordRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "invalid JSON body")
		return
	}
	if len(req.NewPassword) < 8 {
		response.BadRequest(c, "new password must be at least 8 characters")
		return
	}

	if err := auth.CheckPassword(user.PasswordHash, req.CurrentPassword); err != nil {
		response.Unauthorized(c, "current password is incorrect")
		return
	}

	hash, err := auth.HashPassword(req.NewPassword)
	if err != nil {
		response.InternalError(c, "failed to hash password")
		return
	}

	if err := h.db.Model(&user).Update("password_hash", hash).Error; err != nil {
		response.InternalError(c, "failed to update password")
		return
	}

	response.OK(c, gin.H{"message": "password updated"})
}

func (h *AuthHandler) DeleteMe(c *gin.Context) {
	user, ok := h.currentUser(c)
	if !ok {
		return
	}

	err := h.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("user_id = ?", user.ID).Delete(&models.RefreshToken{}).Error; err != nil {
			return err
		}
		return tx.Delete(&user).Error
	})
	if err != nil {
		response.InternalError(c, "failed to delete account")
		return
	}

	response.OK(c, gin.H{"message": "account deleted"})
}

func (h *AuthHandler) issueTokens(userID uuid.UUID) (tokenResponse, error) {
	accessToken, err := auth.GenerateAccessToken(userID, h.jwtSecret)
	if err != nil {
		return tokenResponse{}, err
	}

	refreshToken, err := auth.GenerateRefreshToken()
	if err != nil {
		return tokenResponse{}, err
	}

	stored := models.RefreshToken{
		UserID:    userID,
		TokenHash: auth.HashRefreshToken(refreshToken),
		ExpiresAt: time.Now().Add(config.RefreshTokenTTL),
		Revoked:   false,
	}
	if err := h.db.Create(&stored).Error; err != nil {
		return tokenResponse{}, err
	}

	return tokenResponse{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		ExpiresIn:    int(config.AccessTokenTTL.Seconds()),
	}, nil
}

func (h *AuthHandler) currentUser(c *gin.Context) (models.User, bool) {
	rawID, exists := c.Get(middleware.UserIDKey)
	if !exists {
		response.Unauthorized(c, "missing user context")
		return models.User{}, false
	}

	userID, ok := rawID.(uuid.UUID)
	if !ok {
		response.Unauthorized(c, "invalid user context")
		return models.User{}, false
	}

	var user models.User
	if err := h.db.First(&user, "id = ?", userID).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			response.NotFound(c, "user not found")
			return models.User{}, false
		}
		response.InternalError(c, "failed to lookup user")
		return models.User{}, false
	}

	return user, true
}

func publicUser(user models.User) gin.H {
	return gin.H{
		"id":         user.ID,
		"email":      user.Email,
		"name":       user.Name,
		"created_at": user.CreatedAt,
	}
}

func isValidEmail(email string) bool {
	return strings.Contains(email, "@") && len(email) >= 3
}

func isDuplicateKeyError(err error) bool {
	return strings.Contains(err.Error(), "duplicate key") ||
		strings.Contains(err.Error(), "UNIQUE constraint")
}
