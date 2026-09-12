package security

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidToken = errors.New("invalid token")
	ErrTokenExpired = errors.New("token expired")
)

// Claims is the JWT payload for an access token. It carries just enough to
// authorize a request without a database lookup: who the user is, their
// role, and (for a tech specialist) their assigned support line.
type Claims struct {
	Subject   string `json:"sub"`
	Role      string `json:"role"`
	Line      string `json:"line,omitempty"`
	IssuedAt  int64  `json:"iat"`
	ExpiresAt int64  `json:"exp"`
}

type jwtHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
}

var accessTokenHeader = jwtHeader{Alg: "HS256", Typ: "JWT"}

// SignToken produces a standard three-part HS256 JWT (header.payload.sig,
// base64url without padding). It is a small hand-rolled implementation
// rather than a third-party JWT library so the backend has zero new go.mod
// dependencies and keeps building/testing fully offline.
func SignToken(claims Claims, secret string) (string, error) {
	headerJSON, err := json.Marshal(accessTokenHeader)
	if err != nil {
		return "", err
	}
	payloadJSON, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	unsigned := b64(headerJSON) + "." + b64(payloadJSON)
	return unsigned + "." + sign(unsigned, secret), nil
}

// ParseToken verifies the signature and expiry of a token produced by
// SignToken and returns its claims.
func ParseToken(token, secret string) (Claims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return Claims{}, ErrInvalidToken
	}
	unsigned := parts[0] + "." + parts[1]
	expected := sign(unsigned, secret)
	if subtle.ConstantTimeCompare([]byte(expected), []byte(parts[2])) != 1 {
		return Claims{}, ErrInvalidToken
	}
	payloadJSON, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return Claims{}, ErrInvalidToken
	}
	var claims Claims
	if err := json.Unmarshal(payloadJSON, &claims); err != nil {
		return Claims{}, ErrInvalidToken
	}
	if claims.ExpiresAt > 0 && time.Now().Unix() > claims.ExpiresAt {
		return Claims{}, ErrTokenExpired
	}
	return claims, nil
}

func sign(unsigned, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(unsigned))
	return b64(mac.Sum(nil))
}

func b64(data []byte) string {
	return base64.RawURLEncoding.EncodeToString(data)
}

// NewOpaqueToken returns a random 256-bit refresh token. Only its SHA-256
// hash (HashToken) is ever persisted, so a stolen database dump cannot be
// replayed as a session.
func NewOpaqueToken() (string, error) {
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

// HashToken returns the hex-encoded SHA-256 digest of a refresh token, used
// as the lookup key/storage form in the refresh_tokens table.
func HashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}
