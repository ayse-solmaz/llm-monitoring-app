package llmadmin

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestValidateUpdateRejectsUnknownAdapter(t *testing.T) {
	req := &updateRequest{AdapterID: "unknown", SystemPrompt: "hi"}
	if err := validateUpdate(req); err == nil {
		t.Fatal("expected error for unknown adapter")
	}
}

func TestValidateUpdateClampsSampling(t *testing.T) {
	req := &updateRequest{
		AdapterID:    "deepkwiki",
		SystemPrompt: "test",
		MaxTokens:    999,
		Temperature:  -1,
		TopP:         0,
	}
	if err := validateUpdate(req); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if req.MaxTokens != 512 || req.Temperature != 0 || req.TopP != 0.9 {
		t.Fatalf("clamping failed: %+v", req)
	}
}

func TestPutSettingsBadJSON(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodPut, "/admin/llm-settings", bytes.NewBufferString("{"))
	rec := httptest.NewRecorder()
	h.PutSettings(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status %d, want 400", rec.Code)
	}
	var env struct {
		Error *struct {
			Code string `json:"code"`
		} `json:"error"`
	}
	if err := json.NewDecoder(rec.Body).Decode(&env); err != nil {
		t.Fatal(err)
	}
	if env.Error == nil || env.Error.Code != "bad_request" {
		t.Fatalf("expected bad_request envelope, got %+v", env)
	}
}
