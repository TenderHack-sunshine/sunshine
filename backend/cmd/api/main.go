package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/adapter"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/application"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/config"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/rag"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/security"
	httptransport "github.com/TenderHack-sunshine/sunshine/backend/internal/transport/http"
	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	settings, err := config.Load()
	if err != nil {
		slog.Error("invalid configuration", "error", err)
		os.Exit(1)
	}
	pool, err := pgxpool.New(context.Background(), settings.DatabaseURL)
	if err != nil {
		slog.Error("connect database", "error", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := pool.Ping(context.Background()); err != nil {
		slog.Error("ping database", "error", err)
		os.Exit(1)
	}

	store := adapter.NewPostgresStore(pool)
	authService := application.NewAuthService(store, application.AuthConfig{
		JWTSecret:       settings.JWTSecret,
		AccessTokenTTL:  settings.AccessTokenTTL,
		RefreshTokenTTL: settings.RefreshTokenTTL,
	})
	adminService := application.NewAdminService(store)
	support := application.NewSupportService(store, rag.NewClient(settings.RAGServiceURL, settings.RAGServiceTimeout))
	tickets := application.NewTicketService(store)
	feedback := application.NewFeedbackService(store)
	analytics := application.NewAnalyticsService(store)

	if settings.AdminEmail != "" && settings.AdminPassword != "" {
		if err := bootstrapAdmin(context.Background(), store, settings); err != nil {
			slog.Error("bootstrap admin account failed", "error", err)
		} else {
			slog.Info("admin account ready", "email", settings.AdminEmail)
		}
	}

	handler := httptransport.NewServer(support, tickets, feedback, analytics, authService, adminService, settings.FrontendOrigin, settings.CookieSecure, slog.Default())
	server := &http.Server{Addr: ":" + settings.Port, Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 30 * time.Second}
	slog.Info("support API listening", "address", server.Addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		slog.Error("server stopped", "error", err)
		os.Exit(1)
	}
}

// bootstrapAdmin makes sure ADMIN_EMAIL/ADMIN_PASSWORD (when both are set)
// resolves to an admin account, so a fresh deployment always has at least
// one admin able to approve tech specialists and grant roles without a
// manual database edit. It is idempotent: re-running it just makes sure the
// account still has the admin role.
func bootstrapAdmin(ctx context.Context, store port.Store, settings config.Config) error {
	existing, err := store.GetUserByEmail(ctx, settings.AdminEmail)
	if err == nil {
		if existing.Role == domain.RoleAdmin {
			return nil
		}
		return store.UpdateUserRole(ctx, existing.ID, domain.RoleAdmin, domain.SupportLineNone, domain.SpecialistStatusNone)
	}
	if !errors.Is(err, application.ErrNotFound) {
		return err
	}
	hash, err := security.HashPassword(settings.AdminPassword)
	if err != nil {
		return err
	}
	id, err := randomID()
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	return store.CreateUser(ctx, domain.User{
		ID: id, Email: settings.AdminEmail, PasswordHash: hash,
		DisplayName: strings.TrimSpace(settings.AdminDisplayName), Role: domain.RoleAdmin,
		CreatedAt: now, UpdatedAt: now,
	})
}

func randomID() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}
