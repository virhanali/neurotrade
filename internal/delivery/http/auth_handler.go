package http

import (
	"context"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"golang.org/x/crypto/bcrypt"

	"neurotrade/internal/domain"
	"neurotrade/internal/middleware"
)

// AuthHandler handles authentication-related requests
type AuthHandler struct {
	userRepo domain.UserRepository
}

// NewAuthHandler creates a new AuthHandler
func NewAuthHandler(userRepo domain.UserRepository) *AuthHandler {
	return &AuthHandler{
		userRepo: userRepo,
	}
}

// LoginRequest represents the login request payload
type LoginRequest struct {
	Username string `json:"username" validate:"required"`
	Password string `json:"password" validate:"required"`
}

// LoginResponse represents the login response
type LoginResponse struct {
	Token string      `json:"token"`
	User  *UserOutput `json:"user"`
}

// UserOutput represents user data in API responses
type UserOutput struct {
	ID           string  `json:"id"`
	Username     string  `json:"username"`
	Role         string  `json:"role"`
	Mode         string  `json:"mode"`
	PaperBalance float64 `json:"paper_balance"`
}

// Login handles user login
// POST /api/auth/login
func (h *AuthHandler) Login(c echo.Context) error {
	var req LoginRequest
	if err := c.Bind(&req); err != nil {
		return BadRequestResponse(c, "Invalid request payload")
	}

	// Validate input
	if req.Username == "" || req.Password == "" {
		return BadRequestResponse(c, "Username and password are required")
	}

	// Get user by username
	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	user, err := h.userRepo.GetByUsername(ctx, req.Username)
	if err != nil {
		return UnauthorizedResponse(c, "Invalid credentials")
	}

	// Verify password
	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		return UnauthorizedResponse(c, "Invalid credentials")
	}

	// Generate JWT token
	token, err := middleware.GenerateJWT(user.ID, user.Role)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to generate token", err)
	}

	// Set HTTP-only cookie
	cookie := &http.Cookie{
		Name:     "token",
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		Secure:   false, // Set to true in production with HTTPS
		SameSite: http.SameSiteStrictMode,
		MaxAge:   86400, // 24 hours
	}
	c.SetCookie(cookie)

	// Return response
	return SuccessResponse(c, LoginResponse{
		Token: token,
		User: &UserOutput{
			ID:           user.ID.String(),
			Username:     user.Username,
			Role:         user.Role,
			Mode:         user.Mode,
			PaperBalance: user.PaperBalance,
		},
	})
}

// Logout handles user logout
// POST /api/auth/logout
func (h *AuthHandler) Logout(c echo.Context) error {
	// Clear the cookie
	cookie := &http.Cookie{
		Name:     "token",
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		MaxAge:   -1, // Delete cookie
	}
	c.SetCookie(cookie)

	// Redirect to login page
	return c.Redirect(http.StatusFound, "/login")
}

// Register handles user registration (for future use)
// POST /api/auth/register
func (h *AuthHandler) Register(c echo.Context) error {
	type RegisterRequest struct {
		Username string `json:"username" validate:"required"`
		Password string `json:"password" validate:"required,min=6"`
	}

	var req RegisterRequest
	if err := c.Bind(&req); err != nil {
		return BadRequestResponse(c, "Invalid request payload")
	}

	// Validate input
	if req.Username == "" || req.Password == "" {
		return BadRequestResponse(c, "Username and password are required")
	}

	if len(req.Password) < 6 {
		return BadRequestResponse(c, "Password must be at least 6 characters")
	}

	// Hash password
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		return InternalServerErrorResponse(c, "Failed to hash password", err)
	}

	// Create user
	ctx, cancel := context.WithTimeout(c.Request().Context(), 5*time.Second)
	defer cancel()

	user := &domain.User{
		ID:           uuid.New(),
		Username:     req.Username,
		PasswordHash: string(hashedPassword),
		Role:         domain.RoleUser,
		PaperBalance: 1000.0, // Default paper balance
		Mode:         domain.ModePaper,
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	if err := h.userRepo.Create(ctx, user); err != nil {
		return InternalServerErrorResponse(c, "Failed to create user", err)
	}

	return CreatedResponse(c, map[string]string{
		"message":  "User registered successfully",
		"username": user.Username,
	})
}
