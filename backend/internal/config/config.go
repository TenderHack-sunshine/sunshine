package config

import (
	"errors"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Port             string
	DatabaseURL      string
	AIServiceURL     string
	AIServiceTimeout time.Duration
}

func Load() (Config, error) {
	timeoutSeconds, err := strconv.Atoi(value("AI_SERVICE_TIMEOUT", "15"))
	if err != nil || timeoutSeconds < 1 {
		return Config{}, errors.New("AI_SERVICE_TIMEOUT must be a positive number of seconds")
	}
	config := Config{Port: value("PORT", "8080"), DatabaseURL: strings.TrimSpace(os.Getenv("DATABASE_URL")), AIServiceURL: strings.TrimSpace(os.Getenv("AI_SERVICE_URL")), AIServiceTimeout: time.Duration(timeoutSeconds) * time.Second}
	if config.DatabaseURL == "" {
		return Config{}, errors.New("DATABASE_URL is required")
	}
	if config.AIServiceURL == "" {
		return Config{}, errors.New("AI_SERVICE_URL is required")
	}
	return config, nil
}

func value(name, fallback string) string {
	if result := strings.TrimSpace(os.Getenv(name)); result != "" {
		return result
	}
	return fallback
}
