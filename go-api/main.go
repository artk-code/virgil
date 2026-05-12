// Package main is a minimal API template: health checks, Redis ping, Postgres ping.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/go-redis/redis/v8"
	_ "github.com/lib/pq"
)

type healthResponse struct {
	Status  string `json:"status"`
	Redis   string `json:"redis"`
	Postgres string `json:"postgres"`
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/ready", handleHealth)

	addr := ":8080"
	log.Printf("go-api listening on %s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	redisStatus := pingRedis(ctx)
	pgStatus := pingPostgres(ctx)

	status := http.StatusOK
	if redisStatus != "ok" || pgStatus != "ok" {
		status = http.StatusServiceUnavailable
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(healthResponse{
		Status:   map[bool]string{true: "ok", false: "degraded"}[status == http.StatusOK],
		Redis:    redisStatus,
		Postgres: pgStatus,
	})
}

func pingRedis(ctx context.Context) string {
	u := os.Getenv("REDIS_URL")
	if u == "" {
		return "skipped"
	}
	opt, err := redis.ParseURL(u)
	if err != nil {
		return "misconfigured"
	}
	c := redis.NewClient(opt)
	defer c.Close()
	if err := c.Ping(ctx).Err(); err != nil {
		return "error"
	}
	return "ok"
}

func pingPostgres(ctx context.Context) string {
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		return "skipped"
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return "misconfigured"
	}
	defer db.Close()
	if err := db.PingContext(ctx); err != nil {
		return "error"
	}
	return "ok"
}
