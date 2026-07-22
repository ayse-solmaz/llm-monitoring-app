package appcompat

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/masterfabric-go/masterfabric/internal/application/iam/dto"
	"github.com/masterfabric-go/masterfabric/internal/application/iam/usecase"
	infraAuth "github.com/masterfabric-go/masterfabric/internal/infrastructure/auth"
	iamRepo "github.com/masterfabric-go/masterfabric/internal/domain/iam/repository"
	"github.com/masterfabric-go/masterfabric/internal/domain/iam/service"
	"github.com/masterfabric-go/masterfabric/internal/domain/iam/model"
	"github.com/masterfabric-go/masterfabric/internal/shared/middleware"
	"github.com/masterfabric-go/masterfabric/internal/shared/response"
	domainErr "github.com/masterfabric-go/masterfabric/internal/shared/errors"
)

const (
	accessTokenTTL  = 15 * time.Minute
	refreshTokenTTL = 7 * 24 * time.Hour
	minPasswordLen  = 8
	maxPasswordLen  = 128
	maxEmailLen     = 254
)

var emailRegex = regexp.MustCompile(`^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$`)

type AuthHandler struct {
	db         *pgxpool.Pool
	jwt        *infraAuth.JWTService
	registerUC *usecase.RegisterUseCase
	userRepo   iamRepo.UserRepository
}

func NewAuthHandler(
	db *pgxpool.Pool,
	jwt *infraAuth.JWTService,
	registerUC *usecase.RegisterUseCase,
	userRepo iamRepo.UserRepository,
) *AuthHandler {
	return &AuthHandler{db: db, jwt: jwt, registerUC: registerUC, userRepo: userRepo}
}

type registerBody struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
}

type loginBody struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type refreshBody struct {
	RefreshToken string `json:"refresh_token"`
}

type updateProfileBody struct {
	Name string `json:"name"`
}

type changePasswordBody struct {
	CurrentPassword string `json:"current_password"`
	NewPassword     string `json:"new_password"`
}

type tokenData struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
}

type userData struct {
	ID        uuid.UUID `json:"id"`
	Email     string    `json:"email"`
	Name      string    `json:"name"`
	CreatedAt time.Time `json:"created_at"`
}

func (h *AuthHandler) Register(w http.ResponseWriter, r *http.Request) {
	var req registerBody
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}

	email := normalizeEmail(req.Email)
	if !isValidEmail(email) {
		response.EnvelopeBadRequest(w, "invalid email")
		return
	}
	if msg := validatePassword(req.Password); msg != "" {
		response.EnvelopeBadRequest(w, msg)
		return
	}

	first, last := splitName(req.Name)
	user, err := h.registerUC.Execute(r.Context(), dto.RegisterRequest{
		Email:     email,
		Password:  req.Password,
		FirstName: first,
		LastName:  last,
	})
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "already") {
			response.EnvelopeConflict(w, "email already registered")
			return
		}
		response.EnvelopeInternal(w, "failed to create user")
		return
	}

	response.EnvelopeCreated(w, userData{
		ID:        user.ID,
		Email:     user.Email,
		Name:      strings.TrimSpace(user.FirstName + " " + user.LastName),
		CreatedAt: user.CreatedAt,
	})
}

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var req loginBody
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}

	user, err := h.userRepo.GetByEmail(r.Context(), normalizeEmail(req.Email))
	if err != nil {
		response.EnvelopeUnauthorized(w, "invalid email or password")
		return
	}
	if !user.IsActive() {
		response.EnvelopeUnauthorized(w, "invalid email or password")
		return
	}
	if err := h.jwt.VerifyPassword(user.PasswordHash, req.Password); err != nil {
		response.EnvelopeUnauthorized(w, "invalid email or password")
		return
	}

	tokens, err := h.issueTokens(r.Context(), user.ID, user.Email)
	if err != nil {
		response.EnvelopeInternal(w, "failed to issue tokens")
		return
	}
	response.EnvelopeOK(w, tokens)
}

func (h *AuthHandler) Refresh(w http.ResponseWriter, r *http.Request) {
	var req refreshBody
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}
	if req.RefreshToken == "" {
		response.EnvelopeBadRequest(w, "refresh_token is required")
		return
	}

	hash := infraAuth.HashRefreshToken(req.RefreshToken)
	var stored struct {
		ID     uuid.UUID
		UserID uuid.UUID
		Revoked bool
		ExpiresAt time.Time
	}
	err := h.db.QueryRow(r.Context(), `
		SELECT id, user_id, revoked, expires_at FROM refresh_tokens WHERE token_hash = $1
	`, hash).Scan(&stored.ID, &stored.UserID, &stored.Revoked, &stored.ExpiresAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			response.EnvelopeUnauthorized(w, "invalid refresh token")
			return
		}
		response.EnvelopeInternal(w, "failed to refresh token")
		return
	}
	if stored.Revoked || time.Now().After(stored.ExpiresAt) {
		response.EnvelopeUnauthorized(w, "invalid refresh token")
		return
	}

	user, err := h.userRepo.GetByID(r.Context(), stored.UserID)
	if err != nil {
		response.EnvelopeUnauthorized(w, "invalid refresh token")
		return
	}

	newRefresh, err := infraAuth.GenerateRefreshToken()
	if err != nil {
		response.EnvelopeInternal(w, "failed to refresh token")
		return
	}

	access, err := h.jwt.GenerateTokenWithTTL(r.Context(), service.TokenClaims{
		UserID: user.ID,
		Email:  user.Email,
	}, accessTokenTTL)
	if err != nil {
		response.EnvelopeInternal(w, "failed to refresh token")
		return
	}

	tx, err := h.db.Begin(r.Context())
	if err != nil {
		response.EnvelopeInternal(w, "failed to refresh token")
		return
	}
	defer tx.Rollback(r.Context())

	if _, err := tx.Exec(r.Context(), `UPDATE refresh_tokens SET revoked = TRUE WHERE id = $1`, stored.ID); err != nil {
		response.EnvelopeInternal(w, "failed to refresh token")
		return
	}
	if _, err := tx.Exec(r.Context(), `
		INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, revoked)
		VALUES ($1, $2, $3, $4, FALSE)
	`, uuid.New(), stored.UserID, infraAuth.HashRefreshToken(newRefresh), time.Now().Add(refreshTokenTTL)); err != nil {
		response.EnvelopeInternal(w, "failed to refresh token")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		response.EnvelopeInternal(w, "failed to refresh token")
		return
	}

	response.EnvelopeOK(w, tokenData{
		AccessToken:  access,
		RefreshToken: newRefresh,
		ExpiresIn:    int(accessTokenTTL.Seconds()),
	})
}

func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	var req refreshBody
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}
	if req.RefreshToken == "" {
		response.EnvelopeBadRequest(w, "refresh_token is required")
		return
	}

	hash := infraAuth.HashRefreshToken(req.RefreshToken)
	_, _ = h.db.Exec(r.Context(), `
		UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1 AND revoked = FALSE
	`, hash)

	response.EnvelopeOK(w, map[string]string{"message": "logged out"})
}

func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}
	response.EnvelopeOK(w, toUserData(user))
}

func (h *AuthHandler) UpdateMe(w http.ResponseWriter, r *http.Request) {
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}

	var req updateProfileBody
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}

	name := strings.TrimSpace(req.Name)
	if name == "" {
		response.EnvelopeBadRequest(w, "name is required")
		return
	}

	first, last := splitName(name)
	user.FirstName = first
	user.LastName = last
	if err := h.userRepo.Update(r.Context(), user); err != nil {
		response.EnvelopeInternal(w, "failed to update profile")
		return
	}

	response.EnvelopeOK(w, toUserData(user))
}

func (h *AuthHandler) ChangePassword(w http.ResponseWriter, r *http.Request) {
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}

	var req changePasswordBody
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.EnvelopeBadRequest(w, "invalid JSON body")
		return
	}
	if msg := validatePassword(req.NewPassword); msg != "" {
		response.EnvelopeBadRequest(w, msg)
		return
	}

	if err := h.jwt.VerifyPassword(user.PasswordHash, req.CurrentPassword); err != nil {
		response.EnvelopeUnauthorized(w, "current password is incorrect")
		return
	}

	hash, err := h.jwt.HashPassword(req.NewPassword)
	if err != nil {
		response.EnvelopeInternal(w, "failed to hash password")
		return
	}

	tx, err := h.db.Begin(r.Context())
	if err != nil {
		response.EnvelopeInternal(w, "failed to update password")
		return
	}
	defer tx.Rollback(r.Context())

	if _, err := tx.Exec(r.Context(), `
		UPDATE users SET password_hash = $1, updated_at = $2 WHERE id = $3
	`, hash, time.Now().UTC(), user.ID); err != nil {
		response.EnvelopeInternal(w, "failed to update password")
		return
	}
	if _, err := tx.Exec(r.Context(), `
		UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1 AND revoked = FALSE
	`, user.ID); err != nil {
		response.EnvelopeInternal(w, "failed to update password")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		response.EnvelopeInternal(w, "failed to update password")
		return
	}

	response.EnvelopeOK(w, map[string]string{"message": "password updated"})
}

func (h *AuthHandler) DeleteMe(w http.ResponseWriter, r *http.Request) {
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}

	if err := h.userRepo.Delete(r.Context(), user.ID); err != nil {
		response.EnvelopeInternal(w, "failed to delete account")
		return
	}

	response.EnvelopeOK(w, map[string]string{"message": "account deleted"})
}

func (h *AuthHandler) currentUser(w http.ResponseWriter, r *http.Request) (*model.User, bool) {
	userID, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		response.EnvelopeUnauthorized(w, "not authenticated")
		return nil, false
	}

	user, err := h.userRepo.GetByID(r.Context(), userID)
	if err != nil {
		if errors.Is(err, domainErr.ErrNotFound) {
			response.EnvelopeNotFound(w, "user not found")
			return nil, false
		}
		response.EnvelopeInternal(w, "failed to lookup user")
		return nil, false
	}

	return user, true
}

func toUserData(user *model.User) userData {
	return userData{
		ID:        user.ID,
		Email:     user.Email,
		Name:      strings.TrimSpace(user.FirstName + " " + user.LastName),
		CreatedAt: user.CreatedAt,
	}
}

func (h *AuthHandler) issueTokens(ctx context.Context, userID uuid.UUID, email string) (tokenData, error) {
	access, err := h.jwt.GenerateTokenWithTTL(ctx, service.TokenClaims{
		UserID: userID,
		Email:  email,
	}, accessTokenTTL)
	if err != nil {
		return tokenData{}, err
	}

	refresh, err := infraAuth.GenerateRefreshToken()
	if err != nil {
		return tokenData{}, err
	}

	_, err = h.db.Exec(ctx, `
		INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, revoked)
		VALUES ($1, $2, $3, $4, FALSE)
	`, uuid.New(), userID, infraAuth.HashRefreshToken(refresh), time.Now().Add(refreshTokenTTL))
	if err != nil {
		return tokenData{}, err
	}

	return tokenData{
		AccessToken:  access,
		RefreshToken: refresh,
		ExpiresIn:    int(accessTokenTTL.Seconds()),
	}, nil
}

func normalizeEmail(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}

func isValidEmail(email string) bool {
	return len(email) <= maxEmailLen && emailRegex.MatchString(email)
}

func validatePassword(password string) string {
	if len(password) < minPasswordLen {
		return "password must be at least 8 characters"
	}
	if len(password) > maxPasswordLen {
		return "password must be at most 128 characters"
	}
	return ""
}

func splitName(name string) (string, string) {
	name = strings.TrimSpace(name)
	if name == "" {
		return "User", ""
	}
	parts := strings.Fields(name)
	if len(parts) == 1 {
		return parts[0], ""
	}
	return parts[0], strings.Join(parts[1:], " ")
}
