package mcp

import (
	"context"
	"testing"
)

func TestValidateRejectsEmpty(t *testing.T) {
	if err := Validate(&MCPPayload{}); err == nil {
		t.Fatal("expected error")
	}
}

func TestValidateAndClamp(t *testing.T) {
	req := &MCPPayload{
		Messages:    []Message{{Role: "user", Content: "hi"}},
		MaxTokens:   9999,
		Temperature: -1,
		TopP:        0,
		AdapterID:   "deepkwiki",
	}
	if err := Validate(req); err != nil {
		t.Fatal(err)
	}
	if req.MaxTokens != 512 {
		t.Fatalf("MaxTokens=%d", req.MaxTokens)
	}
	if req.Temperature != 0 {
		t.Fatalf("Temperature=%v", req.Temperature)
	}
	if req.TopP != 0.9 {
		t.Fatalf("TopP=%v", req.TopP)
	}
	if req.Model != "/app/model" {
		t.Fatalf("Model=%s", req.Model)
	}
}

func TestValidateUnknownAdapter(t *testing.T) {
	err := Validate(&MCPPayload{
		Messages:  []Message{{Role: "user", Content: "hi"}},
		AdapterID: "nope",
	})
	if err == nil {
		t.Fatal("expected unknown adapter error")
	}
}

func TestApplyAdapterDeepKwiki(t *testing.T) {
	req := &MCPPayload{
		Messages:  []Message{{Role: "user", Content: "What is gateway?"}},
		AdapterID: "deepkwiki",
	}
	ApplyAdapter(req)
	if !contains(req.Messages[0].Content, "DeepKwiki") {
		t.Fatalf("missing DeepKwiki hint: %s", req.Messages[0].Content)
	}
	if !contains(req.Messages[0].Content, "What is gateway?") {
		t.Fatal("missing original question")
	}
}

func TestHandleMCPRequestWithoutMLCURL(t *testing.T) {
	t.Setenv("MLC_URL", "")
	res, err := HandleMCPRequest(context.Background(), MCPPayload{
		Messages:  []Message{{Role: "user", Content: "hello"}},
		AdapterID: "code-assistant",
	})
	if err != nil {
		t.Fatal(err)
	}
	if res.Meta["status"] != "validated" {
		t.Fatalf("status=%s", res.Meta["status"])
	}
	if res.AdapterID != "code-assistant" {
		t.Fatalf("adapter=%s", res.AdapterID)
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(sub) == 0 ||
		(len(s) > 0 && (func() bool {
			for i := 0; i+len(sub) <= len(s); i++ {
				if s[i:i+len(sub)] == sub {
					return true
				}
			}
			return false
		})()))
}
