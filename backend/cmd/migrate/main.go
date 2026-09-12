package main

import (
	"context"
	"log"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/config"
	"github.com/TenderHack-sunshine/sunshine/backend/migrations"
	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	databaseURL, err := config.LoadDatabaseURL()
	if err != nil {
		log.Fatal(err)
	}
	pool, err := pgxpool.New(context.Background(), databaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer pool.Close()
	for _, migration := range migrations.All() {
		if _, err := pool.Exec(context.Background(), migration.SQL); err != nil {
			log.Fatalf("apply %s: %v", migration.Name, err)
		}
		log.Printf("applied %s", migration.Name)
	}
}
