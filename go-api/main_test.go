package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHealthHandler(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rr := httptest.NewRecorder()
	s := &server{db: nil, redisURL: ""}
	s.handleHealth(rr, req)
	if rr.Code != http.StatusOK && rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("unexpected status %d", rr.Code)
	}
}

func TestCheckinRejectsNonPost(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/v1/agents/checkin", nil)
	rr := httptest.NewRecorder()

	s := &server{db: nil, redisURL: ""}
	s.handleCheckin(rr, req)

	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected %d got %d", http.StatusMethodNotAllowed, rr.Code)
	}
}

func TestParseLimitScenarios(t *testing.T) {
	tests := []struct {
		name       string
		rawLimit   string
		rawOffset  string
		wantLimit  int
		wantOffset int
		wantErr    bool
	}{
		{name: "empty uses fallback", rawLimit: "", rawOffset: "", wantLimit: 50, wantOffset: 0},
		{name: "invalid limit", rawLimit: "abc", rawOffset: "", wantErr: true},
		{name: "negative limit", rawLimit: "-2", rawOffset: "", wantErr: true},
		{name: "over max limit", rawLimit: "999", rawOffset: "", wantErr: true},
		{name: "valid values", rawLimit: "42", rawOffset: "12", wantLimit: 42, wantOffset: 12},
		{name: "negative offset", rawLimit: "42", rawOffset: "-1", wantErr: true},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			url := "/api/v1/events/search"
			query := ""
			if tc.rawLimit != "" {
				query = "limit=" + tc.rawLimit
			}
			if tc.rawOffset != "" {
				if query != "" {
					query += "&"
				}
				query += "offset=" + tc.rawOffset
			}
			if query != "" {
				url += "?" + query
			}
			req := httptest.NewRequest(http.MethodGet, url, nil)
			limit, offset, err := parseLimitOffset(req, 50, 250, 10000)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if limit != tc.wantLimit || offset != tc.wantOffset {
				t.Fatalf("want limit=%d offset=%d got limit=%d offset=%d", tc.wantLimit, tc.wantOffset, limit, offset)
			}
		})
	}
}

func TestWriteJSONSetsContentType(t *testing.T) {
	rr := httptest.NewRecorder()
	writeJSON(rr, http.StatusCreated, map[string]string{"status": "ok"})
	if rr.Code != http.StatusCreated {
		t.Fatalf("expected status %d got %d", http.StatusCreated, rr.Code)
	}
	if rr.Header().Get("Content-Type") != "application/json" {
		t.Fatalf("unexpected content type %q", rr.Header().Get("Content-Type"))
	}
	var payload map[string]string
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("expected valid json: %v", err)
	}
	if payload["status"] != "ok" {
		t.Fatalf("unexpected payload %v", payload)
	}
}

func TestRecentAlertsInvalidLimitReturnsContractError(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/v1/alerts/recent?limit=abc", nil)
	rr := httptest.NewRecorder()

	s := &server{db: nil, redisURL: ""}
	s.handleRecentAlerts(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected %d got %d", http.StatusBadRequest, rr.Code)
	}
	var payload map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("expected valid json: %v", err)
	}
	if payload["error_code"] != "invalid_query" {
		t.Fatalf("unexpected payload %v", payload)
	}
}

func TestEventSearchInvalidSeverityReturnsContractError(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/v1/events/search?severity=urgent", nil)
	rr := httptest.NewRecorder()

	s := &server{db: nil, redisURL: ""}
	s.handleEventSearch(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected %d got %d", http.StatusBadRequest, rr.Code)
	}
	var payload map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("expected valid json: %v", err)
	}
	if payload["error_code"] != "invalid_query" {
		t.Fatalf("unexpected payload %v", payload)
	}
}
