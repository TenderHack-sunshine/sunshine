package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/adapter"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/application"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/config"
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
	support := application.NewSupportService(store, adapter.NewHTTPAIClient(settings.AIServiceURL, settings.AIServiceTimeout))
	tickets := application.NewTicketService(store)
	feedback := application.NewFeedbackService(store)
	analytics := application.NewAnalyticsService(store)
	server := &http.Server{Addr: ":" + settings.Port, Handler: httptransport.NewServer(support, tickets, feedback, analytics, slog.Default()), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 30 * time.Second}
	slog.Info("support API listening", "address", server.Addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		slog.Error("server stopped", "error", err)
		os.Exit(1)
	}
}
