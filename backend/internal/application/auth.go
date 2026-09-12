package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/security"
)

const (
	minPasswordLength = 8
	maxPasswordLength = 200
	maxNameLength     = 200
)

// AuthConfig holds the values the auth service needs from the process
// environment (see internal/config), kept separate from Config itself so
// this package does not import the config package.
type AuthConfig struct {
	JWTSecret       string
	AccessTokenTTL  time.Duration
	RefreshTokenTTL time.Duration
}

type AuthService struct {
	store  port.Store
	config AuthConfig
	now    func() time.Time
	newID  func() (string, error)
}

func NewAuthService(store port.Store, config AuthConfig) *AuthService {
	return &AuthService{store: store, config: config, now: time.Now, newID: newID}
}

// AuthResult is returned on every successful login/register/refresh. The
// HTTP layer puts AccessToken in the JSON body and RefreshToken in an
// httpOnly cookie; the two are never mixed in the same channel.
type AuthResult struct {
	AccessToken  string
	RefreshToken string
	RefreshTTL   time.Duration
	User         domain.User
}

// Register creates a regular portal user and logs them in immediately.
func (s *AuthService) Register(ctx context.Context, email, password, displayName string) (AuthResult, error) {
	user, err := s.createUser(ctx, email, password, displayName, domain.RoleUser, domain.SupportLineNone, domain.SpecialistStatusNone)
	if err != nil {
		return AuthResult{}, err
	}
	return s.issueTokens(ctx, user)
}

// RegisterSpecialist creates a tech-specialist account in "pending" status.
// It deliberately does not log the user in: Login/Refresh reject pending or
// rejected specialists, so access only starts once an admin approves them
// (AdminService.ApproveSpecialist) or grants the role directly
// (AdminService.SetRole).
func (s *AuthService) RegisterSpecialist(ctx context.Context, email, password, displayName string, line domain.SupportLine) (domain.User, error) {
	if !validLine(line) {
		return domain.User{}, ErrInvalidInput
	}
	return s.createUser(ctx, email, password, displayName, domain.RoleTechSpecialist, line, domain.SpecialistStatusPending)
}

func (s *AuthService) createUser(ctx context.Context, email, password, displayName string, role domain.Role, line domain.SupportLine, status domain.SpecialistStatus) (domain.User, error) {
	email = normalizeEmail(email)
	displayName = strings.TrimSpace(displayName)
	if !validEmail(email) || len(password) < minPasswordLength || len(password) > maxPasswordLength || displayName == "" || len([]rune(displayName)) > maxNameLength {
		return domain.User{}, ErrInvalidInput
	}
	if _, err := s.store.GetUserByEmail(ctx, email); err == nil {
		return domain.User{}, ErrEmailTaken
	} else if !errors.Is(err, ErrNotFound) {
		return domain.User{}, err
	}
	hash, err := security.HashPassword(password)
	if err != nil {
		return domain.User{}, err
	}
	id, err := s.newID()
	if err != nil {
		return domain.User{}, err
	}
	now := s.now().UTC()
	user := domain.User{
		ID: id, Email: email, PasswordHash: hash, DisplayName: displayName,
		Role: role, Line: line, SpecialistStatus: status,
		CreatedAt: now, UpdatedAt: now,
	}
	if err := s.store.CreateUser(ctx, user); err != nil {
		return domain.User{}, err
	}
	user.PasswordHash = ""
	return user, nil
}

// Login verifies credentials and, for an approved account, issues a fresh
// access/refresh token pair.
func (s *AuthService) Login(ctx context.Context, email, password string) (AuthResult, error) {
	user, err := s.store.GetUserByEmail(ctx, normalizeEmail(email))
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return AuthResult{}, ErrInvalidCredentials
		}
		return AuthResult{}, err
	}
	if !security.VerifyPassword(user.PasswordHash, password) {
		return AuthResult{}, ErrInvalidCredentials
	}
	if err := specialistGate(user); err != nil {
		return AuthResult{}, err
	}
	return s.issueTokens(ctx, user)
}

// Refresh rotates a refresh token: the presented token is revoked and a new
// access/refresh pair is issued, so a stolen-and-replayed old cookie fails
// once the legitimate client has refreshed.
func (s *AuthService) Refresh(ctx context.Context, refreshToken string) (AuthResult, error) {
	if strings.TrimSpace(refreshToken) == "" {
		return AuthResult{}, ErrInvalidCredentials
	}
	hash := security.HashToken(refreshToken)
	stored, err := s.store.GetRefreshToken(ctx, hash)
	if err != nil {
		return AuthResult{}, ErrInvalidCredentials
	}
	if stored.RevokedAt != nil || !s.now().UTC().Before(stored.ExpiresAt) {
		return AuthResult{}, ErrInvalidCredentials
	}
	user, err := s.store.GetUserByID(ctx, stored.UserID)
	if err != nil {
		return AuthResult{}, ErrInvalidCredentials
	}
	if err := specialistGate(user); err != nil {
		return AuthResult{}, err
	}
	if err := s.store.RevokeRefreshToken(ctx, hash); err != nil {
		return AuthResult{}, err
	}
	return s.issueTokens(ctx, user)
}

// Logout revokes the presented refresh token. It is intentionally silent
// about an absent/unknown token: the caller (HTTP handler) always clears the
// cookie regardless.
func (s *AuthService) Logout(ctx context.Context, refreshToken string) error {
	if strings.TrimSpace(refreshToken) == "" {
		return nil
	}
	return s.store.RevokeRefreshToken(ctx, security.HashToken(refreshToken))
}

func (s *AuthService) Me(ctx context.Context, userID string) (domain.User, error) {
	user, err := s.store.GetUserByID(ctx, userID)
	if err != nil {
		return domain.User{}, err
	}
	user.PasswordHash = ""
	return user, nil
}

// ParseAccessToken verifies a bearer access token and turns it into an
// Actor. It is the only place the HTTP transport needs to reach into the
// JWT secret, keeping that value out of the transport package entirely.
func (s *AuthService) ParseAccessToken(token string) (Actor, error) {
	claims, err := security.ParseToken(token, s.config.JWTSecret)
	if err != nil {
		return Actor{}, ErrInvalidCredentials
	}
	if strings.TrimSpace(claims.Subject) == "" {
		return Actor{}, ErrInvalidCredentials
	}
	return Actor{UserID: claims.Subject, Role: domain.Role(claims.Role), Line: domain.SupportLine(claims.Line)}, nil
}

func (s *AuthService) issueTokens(ctx context.Context, user domain.User) (AuthResult, error) {
	now := s.now().UTC()
	access, err := security.SignToken(security.Claims{
		Subject:   user.ID,
		Role:      string(user.Role),
		Line:      string(user.Line),
		IssuedAt:  now.Unix(),
		ExpiresAt: now.Add(s.config.AccessTokenTTL).Unix(),
	}, s.config.JWTSecret)
	if err != nil {
		return AuthResult{}, err
	}
	refresh, err := security.NewOpaqueToken()
	if err != nil {
		return AuthResult{}, err
	}
	tokenID, err := s.newID()
	if err != nil {
		return AuthResult{}, err
	}
	if err := s.store.CreateRefreshToken(ctx, domain.RefreshToken{
		ID: tokenID, UserID: user.ID, TokenHash: security.HashToken(refresh),
		ExpiresAt: now.Add(s.config.RefreshTokenTTL), CreatedAt: now,
	}); err != nil {
		return AuthResult{}, err
	}
	user.PasswordHash = ""
	return AuthResult{AccessToken: access, RefreshToken: refresh, RefreshTTL: s.config.RefreshTokenTTL, User: user}, nil
}

// specialistGate blocks sign-in for a tech specialist whose self-registration
// has not been approved yet (or was rejected). Every other role signs in
// freely.
func specialistGate(user domain.User) error {
	if user.Role != domain.RoleTechSpecialist {
		return nil
	}
	switch user.SpecialistStatus {
	case domain.SpecialistStatusApproved:
		return nil
	case domain.SpecialistStatusRejected:
		return ErrRegistrationRejected
	default:
		return ErrPendingApproval
	}
}

func normalizeEmail(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}

// validEmail is a deliberately loose check (one '@', not at either end, no
// whitespace) rather than a full RFC 5322 validator: the only thing that
// actually matters here is that it's a plausible, storable identifier, since
// the account is never confirmed by sending mail to it.
func validEmail(email string) bool {
	at := strings.IndexByte(email, '@')
	return at > 0 && at < len(email)-1 && !strings.ContainsAny(email, " \t\n\r")
}

func validLine(line domain.SupportLine) bool {
	switch line {
	case domain.SupportLineL1, domain.SupportLineL2, domain.SupportLineL3:
		return true
	default:
		return false
	}
}
