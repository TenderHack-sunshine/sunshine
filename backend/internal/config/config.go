package config

import (
	"errors"
	"fmt"
	"os"
	"strings"
	"time"
)

type Config struct {
	Port              string
	DatabaseURL       string
	RAGServiceURL     string
	RAGServiceTimeout time.Duration

	// Authentication.
	JWTSecret       string
	AccessTokenTTL  time.Duration
	RefreshTokenTTL time.Duration
	FrontendOrigin  string
	CookieSecure    bool

	// Optional bootstrap of the first admin account on startup. Both must be
	// set for it to take effect; see cmd/api/main.go.
	AdminEmail       string
	AdminPassword    string
	AdminDisplayName string
}

func Load() (Config, error) {
	timeout, err := parseTimeout(value("RAG_SERVICE_TIMEOUT", "30s"))
	if err != nil {
		return Config{}, err
	}
	databaseURL, err := LoadDatabaseURL()
	if err != nil {
		return Config{}, err
	}
	accessTTL, err := parseDuration("ACCESS_TOKEN_TTL", value("ACCESS_TOKEN_TTL", "15m"))
	if err != nil {
		return Config{}, err
	}
	refreshTTL, err := parseDuration("REFRESH_TOKEN_TTL", value("REFRESH_TOKEN_TTL", "720h"))
	if err != nil {
		return Config{}, err
	}
	config := Config{
		Port:              value("PORT", "8080"),
		DatabaseURL:       databaseURL,
		RAGServiceURL:     strings.TrimSpace(os.Getenv("RAG_SERVICE_URL")),
		RAGServiceTimeout: timeout,
		JWTSecret:         strings.TrimSpace(os.Getenv("JWT_SECRET")),
		AccessTokenTTL:    accessTTL,
		RefreshTokenTTL:   refreshTTL,
		FrontendOrigin:    strings.TrimSpace(os.Getenv("FRONTEND_ORIGIN")),
		CookieSecure:      value("COOKIE_SECURE", "false") == "true",
		AdminEmail:        strings.ToLower(strings.TrimSpace(os.Getenv("ADMIN_EMAIL"))),
		AdminPassword:     os.Getenv("ADMIN_PASSWORD"),
		AdminDisplayName:  value("ADMIN_DISPLAY_NAME", "Администратор"),
	}
	if config.DatabaseURL == "" {
		return Config{}, errors.New("DATABASE_URL is required")
	}
	if config.RAGServiceURL == "" {
		return Config{}, errors.New("RAG_SERVICE_URL is required")
	}
	if len(config.JWTSecret) < 32 {
		return Config{}, errors.New("JWT_SECRET is required and must be at least 32 characters")
	}
	return config, nil
}

// LoadDatabaseURL is used by migrations, which do not need the RAG service.
func LoadDatabaseURL() (string, error) {
	databaseURL := strings.TrimSpace(os.Getenv("DATABASE_URL"))
	if databaseURL == "" {
		return "", errors.New("DATABASE_URL is required")
	}
	return databaseURL, nil
}

func parseTimeout(raw string) (time.Duration, error) {
	raw = strings.TrimSpace(raw)
	if raw != "" && !strings.ContainsAny(raw, "hmsuµn") {
		raw += "s"
	}
	duration, err := time.ParseDuration(raw)
	if err != nil || duration <= 0 {
		return 0, errors.New("RAG_SERVICE_TIMEOUT must be a positive duration, for example 30s")
	}
	return duration, nil
}

func parseDuration(name, raw string) (time.Duration, error) {
	raw = strings.TrimSpace(raw)
	if raw != "" && !strings.ContainsAny(raw, "hmsuµn") {
		raw += "s"
	}
	duration, err := time.ParseDuration(raw)
	if err != nil || duration <= 0 {
		return 0, fmt.Errorf("%s must be a positive duration, for example 30s", name)
	}
	return duration, nil
}

func value(name, fallback string) string {
	if result := strings.TrimSpace(os.Getenv(name)); result != "" {
		return result
	}
	return fallback
}
