package config

import (
	"errors"
	"os"
	"strings"
	"time"
)

type Config struct {
	Port              string
	DatabaseURL       string
	RAGServiceURL     string
	RAGServiceTimeout time.Duration
}

func Load() (Config, error) {
	timeout, err := parseTimeout(value("RAG_SERVICE_TIMEOUT", "30s"))
	if err != nil {
		return Config{}, err
	}
	config := Config{Port: value("PORT", "8080"), DatabaseURL: strings.TrimSpace(os.Getenv("DATABASE_URL")), RAGServiceURL: strings.TrimSpace(os.Getenv("RAG_SERVICE_URL")), RAGServiceTimeout: timeout}
	if config.DatabaseURL == "" {
		return Config{}, errors.New("DATABASE_URL is required")
	}
	if config.RAGServiceURL == "" {
		return Config{}, errors.New("RAG_SERVICE_URL is required")
	}
	return config, nil
}

func parseTimeout(raw string) (time.Duration, error) {
	raw = strings.TrimSpace(raw)
	if raw != "" && !strings.ContainsAny(raw, "hmsuµn") {
		raw += "s"
	}
	timeout, err := time.ParseDuration(raw)
	if err != nil || timeout <= 0 {
		return 0, errors.New("RAG_SERVICE_TIMEOUT must be a positive duration, for example 30s")
	}
	return timeout, nil
}

func value(name, fallback string) string {
	if result := strings.TrimSpace(os.Getenv(name)); result != "" {
		return result
	}
	return fallback
}
