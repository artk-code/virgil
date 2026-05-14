// Package main implements Phase 1 control/query APIs for the security pipeline.
package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	_ "github.com/lib/pq"
)

type server struct {
	db       *sql.DB
	redisURL string
}

type healthResponse struct {
	Status   string `json:"status"`
	Redis    string `json:"redis"`
	Postgres string `json:"postgres"`
}

type apiErrorResponse struct {
	ErrorCode string         `json:"error_code"`
	Message   string         `json:"message"`
	Details   map[string]any `json:"details,omitempty"`
}

type paginationResponse struct {
	Limit    int  `json:"limit"`
	Offset   int  `json:"offset"`
	Returned int  `json:"returned"`
	HasMore  bool `json:"has_more"`
}

func main() {
	srv := &server{
		db:       openPostgres(),
		redisURL: os.Getenv("REDIS_URL"),
	}
	if srv.redisURL == "" {
		srv.redisURL = "redis://redis:6379"
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", srv.handleHealth)
	mux.HandleFunc("/ready", srv.handleHealth)
	mux.HandleFunc("/api/v1/agents/checkin", srv.handleCheckin)
	mux.HandleFunc("/api/v1/agents/", srv.handleAgentStatus)
	mux.HandleFunc("/api/v1/alerts/recent", srv.handleRecentAlerts)
	mux.HandleFunc("/api/v1/events/search", srv.handleEventSearch)

	addr := ":8080"
	log.Printf("go-api listening on %s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}

func openPostgres() *sql.DB {
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		return nil
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		log.Printf("postgres init error: %v", err)
		return nil
	}
	db.SetMaxOpenConns(10)
	db.SetConnMaxLifetime(5 * time.Minute)
	return db
}

func (s *server) handleHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	redisStatus := pingRedis(ctx, s.redisURL)
	pgStatus := pingPostgres(ctx, s.db)

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

func pingRedis(ctx context.Context, u string) string {
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

func pingPostgres(ctx context.Context, db *sql.DB) string {
	if db == nil {
		return "skipped"
	}
	if err := db.PingContext(ctx); err != nil {
		return "error"
	}
	return "ok"
}

type checkinRequest struct {
	AgentID      string   `json:"agent_id"`
	HostID       string   `json:"host_id"`
	SourceType   string   `json:"source_type"`
	Capabilities []string `json:"capabilities"`
}

func (s *server) handleCheckin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method_not_allowed"})
		return
	}
	if s.db == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "database_unavailable"})
		return
	}

	var req checkinRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}
	if strings.TrimSpace(req.AgentID) == "" || strings.TrimSpace(req.HostID) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "agent_id_and_host_id_required"})
		return
	}
	if req.SourceType == "" {
		req.SourceType = "unknown"
	}

	capsJSON, _ := json.Marshal(req.Capabilities)
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "tx_begin_failed"})
		return
	}
	defer tx.Rollback()

	if _, err = tx.ExecContext(
		ctx,
		`INSERT INTO hosts (host_id, first_seen_at, last_seen_at)
		 VALUES ($1, NOW(), NOW())
		 ON CONFLICT (host_id) DO UPDATE SET last_seen_at = NOW()`,
		req.HostID,
	); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "host_upsert_failed"})
		return
	}

	if _, err = tx.ExecContext(
		ctx,
		`INSERT INTO agent_heartbeats (agent_id, host_id, source_type, capabilities, status, seen_at)
		 VALUES ($1, $2, $3, $4::jsonb, 'online', NOW())
		 ON CONFLICT (agent_id) DO UPDATE
		   SET host_id = EXCLUDED.host_id,
		       source_type = EXCLUDED.source_type,
		       capabilities = EXCLUDED.capabilities,
		       status = 'online',
		       seen_at = NOW()`,
		req.AgentID,
		req.HostID,
		req.SourceType,
		string(capsJSON),
	); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "heartbeat_upsert_failed"})
		return
	}
	if err = tx.Commit(); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "tx_commit_failed"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{
		"status":   "ok",
		"agent_id": req.AgentID,
		"host_id":  req.HostID,
	})
}

func (s *server) handleAgentStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method_not_allowed"})
		return
	}
	if s.db == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "database_unavailable"})
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/api/v1/agents/")
	if !strings.HasSuffix(path, "/status") {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not_found"})
		return
	}
	agentID := strings.TrimSuffix(path, "/status")
	agentID = strings.Trim(agentID, "/")
	if agentID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "agent_id_required"})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	var hostID, sourceType, status string
	var capabilitiesRaw []byte
	var seenAt time.Time
	err := s.db.QueryRowContext(
		ctx,
		`SELECT host_id, source_type, capabilities, status, seen_at
		   FROM agent_heartbeats
		  WHERE agent_id = $1`,
		agentID,
	).Scan(&hostID, &sourceType, &capabilitiesRaw, &status, &seenAt)
	if err == sql.ErrNoRows {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "agent_not_found"})
		return
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "query_failed"})
		return
	}
	var capabilities []string
	_ = json.Unmarshal(capabilitiesRaw, &capabilities)

	writeJSON(w, http.StatusOK, map[string]any{
		"agent_id":     agentID,
		"host_id":      hostID,
		"source_type":  sourceType,
		"capabilities": capabilities,
		"status":       status,
		"seen_at":      seenAt.UTC().Format(time.RFC3339),
	})
}

func (s *server) handleRecentAlerts(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeAPIError(w, http.StatusMethodNotAllowed, "method_not_allowed", "only GET is allowed", nil)
		return
	}
	limit, offset, err := parseLimitOffset(r, 20, 100, 10000)
	if err != nil {
		writeAPIError(w, http.StatusBadRequest, "invalid_query", err.Error(), nil)
		return
	}
	if s.db == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "database_unavailable"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 4*time.Second)
	defer cancel()

	rows, err := s.db.QueryContext(
		ctx,
		`SELECT analysis_id, event_id, host_id, severity, score, explanation, analyzed_at
		   FROM security_findings
		  ORDER BY analyzed_at DESC, analysis_id DESC
		  LIMIT $1 OFFSET $2`,
		limit+1,
		offset,
	)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "query_failed"})
		return
	}
	defer rows.Close()

	results := make([]map[string]any, 0, limit+1)
	for rows.Next() {
		var analysisID, eventID, hostID, severity, explanation string
		var score float64
		var analyzedAt time.Time
		if err := rows.Scan(&analysisID, &eventID, &hostID, &severity, &score, &explanation, &analyzedAt); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "scan_failed"})
			return
		}
		results = append(results, map[string]any{
			"analysis_id": analysisID,
			"event_id":    eventID,
			"host_id":     hostID,
			"severity":    severity,
			"score":       score,
			"explanation": explanation,
			"analyzed_at": analyzedAt.UTC().Format(time.RFC3339),
		})
	}
	hasMore := len(results) > limit
	if hasMore {
		results = results[:limit]
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"alerts": results,
		"pagination": paginationResponse{
			Limit:    limit,
			Offset:   offset,
			Returned: len(results),
			HasMore:  hasMore,
		},
	})
}

func (s *server) handleEventSearch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeAPIError(w, http.StatusMethodNotAllowed, "method_not_allowed", "only GET is allowed", nil)
		return
	}
	limit, offset, err := parseLimitOffset(r, 50, 250, 10000)
	if err != nil {
		writeAPIError(w, http.StatusBadRequest, "invalid_query", err.Error(), nil)
		return
	}
	hostID := strings.TrimSpace(r.URL.Query().Get("host_id"))
	eventType := strings.TrimSpace(r.URL.Query().Get("event_type"))
	severity := strings.TrimSpace(r.URL.Query().Get("severity"))
	if severity != "" && !isValidSeverity(severity) {
		writeAPIError(
			w,
			http.StatusBadRequest,
			"invalid_query",
			"severity must be one of: low, medium, high, critical",
			map[string]any{"param": "severity", "value": severity},
		)
		return
	}
	if s.db == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "database_unavailable"})
		return
	}

	var b bytes.Buffer
	b.WriteString(`SELECT event_id, trace_id, host_id, agent_id, source_type, event_type, severity, ts, raw, normalized, tags
	    FROM security_events
	    WHERE 1=1`)
	args := []any{}
	idx := 1
	if hostID != "" {
		b.WriteString(fmt.Sprintf(" AND host_id = $%d", idx))
		args = append(args, hostID)
		idx++
	}
	if eventType != "" {
		b.WriteString(fmt.Sprintf(" AND event_type = $%d", idx))
		args = append(args, eventType)
		idx++
	}
	if severity != "" {
		b.WriteString(fmt.Sprintf(" AND severity = $%d", idx))
		args = append(args, severity)
		idx++
	}
	b.WriteString(fmt.Sprintf(" ORDER BY ts DESC, event_id DESC LIMIT $%d OFFSET $%d", idx, idx+1))
	args = append(args, limit+1, offset)

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	rows, err := s.db.QueryContext(ctx, b.String(), args...)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "query_failed"})
		return
	}
	defer rows.Close()

	results := make([]map[string]any, 0, limit+1)
	for rows.Next() {
		var eventID, traceID, rowHostID, agentID, sourceType, rowEventType, rowSeverity string
		var ts time.Time
		var raw, normalized, tags []byte
		if err := rows.Scan(
			&eventID, &traceID, &rowHostID, &agentID, &sourceType,
			&rowEventType, &rowSeverity, &ts, &raw, &normalized, &tags,
		); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "scan_failed"})
			return
		}
		results = append(results, map[string]any{
			"event_id":    eventID,
			"trace_id":    traceID,
			"host_id":     rowHostID,
			"agent_id":    agentID,
			"source_type": sourceType,
			"event_type":  rowEventType,
			"severity":    rowSeverity,
			"ts":          ts.UTC().Format(time.RFC3339),
			"raw":         decodeJSON(raw),
			"normalized":  decodeJSON(normalized),
			"tags":        decodeJSON(tags),
		})
	}
	hasMore := len(results) > limit
	if hasMore {
		results = results[:limit]
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"events": results,
		"pagination": paginationResponse{
			Limit:    limit,
			Offset:   offset,
			Returned: len(results),
			HasMore:  hasMore,
		},
	})
}

func parseLimitOffset(r *http.Request, fallbackLimit, maxLimit, maxOffset int) (int, int, error) {
	limit, err := parseBoundedInt(r.URL.Query().Get("limit"), fallbackLimit, 1, maxLimit, "limit")
	if err != nil {
		return 0, 0, err
	}
	offset, err := parseBoundedInt(r.URL.Query().Get("offset"), 0, 0, maxOffset, "offset")
	if err != nil {
		return 0, 0, err
	}
	return limit, offset, nil
}

func parseBoundedInt(raw string, fallback, min, max int, name string) (int, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fallback, nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer between %d and %d", name, min, max)
	}
	if n < min || n > max {
		return 0, fmt.Errorf("%s must be between %d and %d", name, min, max)
	}
	return n, nil
}

func isValidSeverity(v string) bool {
	switch strings.ToLower(v) {
	case "low", "medium", "high", "critical":
		return true
	default:
		return false
	}
}

func decodeJSON(raw []byte) any {
	var out any
	if err := json.Unmarshal(raw, &out); err != nil {
		return map[string]any{}
	}
	return out
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeAPIError(w http.ResponseWriter, status int, code, message string, details map[string]any) {
	writeJSON(w, status, apiErrorResponse{
		ErrorCode: code,
		Message:   message,
		Details:   details,
	})
}
