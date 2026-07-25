// Package mcp implements FINAL BOSS Model Context Protocol helpers inside Go.
//
// Live chat still goes browser → KPI gateway → MLC (no new PRD HTTP routes).
// This package mirrors the spec's HandleMCPRequest for validation, adapter
// selection, optional MLC proxy (when MLC_URL is set), and rich result shaping.
package mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// Message is an OpenAI-compatible chat message.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// MCPPayload is the inbound WebMCP-style request.
type MCPPayload struct {
	Messages    []Message `json:"messages"`
	AdapterID   string    `json:"adapter_id"`
	Temperature float64   `json:"temperature"`
	TopP        float64   `json:"top_p"`
	MaxTokens   int       `json:"max_tokens"`
	Model       string    `json:"model"`
	Stream      bool      `json:"stream"`
}

// RichResult is a structured completion for frontend / tooling.
type RichResult struct {
	Content   string            `json:"content"`
	AdapterID string            `json:"adapter_id"`
	Model     string            `json:"model"`
	Usage     map[string]int    `json:"usage,omitempty"`
	Meta      map[string]string `json:"meta,omitempty"`
}

// knownAdapters are soft PEFT ids under peft-adapters/ (CPU demo = prompt style).
var knownAdapters = map[string]string{
	"":               "base",
	"deepkwiki":      "Prefer project docs / DeepKwiki facts; be concise.",
	"code-assistant": "Prefer short code-focused answers with minimal prose.",
}

// Validate checks required fields and clamps sampling params.
func Validate(req *MCPPayload) error {
	if req == nil {
		return fmt.Errorf("payload is nil")
	}
	if len(req.Messages) == 0 {
		return fmt.Errorf("messages required")
	}
	for i, m := range req.Messages {
		if m.Role != "user" && m.Role != "assistant" && m.Role != "system" {
			return fmt.Errorf("messages[%d]: invalid role %q", i, m.Role)
		}
		if strings.TrimSpace(m.Content) == "" {
			return fmt.Errorf("messages[%d]: empty content", i)
		}
	}
	if req.AdapterID != "" {
		if _, ok := knownAdapters[req.AdapterID]; !ok {
			return fmt.Errorf("unknown adapter_id %q", req.AdapterID)
		}
	}
	if req.MaxTokens <= 0 {
		req.MaxTokens = 48
	}
	if req.MaxTokens > 512 {
		req.MaxTokens = 512
	}
	if req.Temperature < 0 {
		req.Temperature = 0
	}
	if req.Temperature > 2 {
		req.Temperature = 2
	}
	if req.TopP <= 0 || req.TopP > 1 {
		req.TopP = 0.9
	}
	if strings.TrimSpace(req.Model) == "" {
		req.Model = "/app/model"
	}
	return nil
}

// ApplyAdapter soft-injects adapter style into the last user message.
func ApplyAdapter(req *MCPPayload) {
	hint, ok := knownAdapters[req.AdapterID]
	if !ok || req.AdapterID == "" || hint == "base" {
		return
	}
	for i := len(req.Messages) - 1; i >= 0; i-- {
		if req.Messages[i].Role == "user" {
			req.Messages[i].Content = hint + "\n\n" + req.Messages[i].Content
			return
		}
	}
}

// HandleMCPRequest validates, applies PEFT adapter selection, optionally proxies
// to MLC via MLC_URL, and returns a RichResult.
func HandleMCPRequest(ctx context.Context, req MCPPayload) (*RichResult, error) {
	if err := Validate(&req); err != nil {
		return nil, err
	}
	ApplyAdapter(&req)

	mlcURL := strings.TrimRight(os.Getenv("MLC_URL"), "/")
	if mlcURL == "" {
		// Offline / CI: return a structured stub so the package is usable without Docker.
		return &RichResult{
			Content:   "",
			AdapterID: req.AdapterID,
			Model:     req.Model,
			Meta: map[string]string{
				"status":  "validated",
				"note":    "MLC_URL unset — validation + adapter only (no proxy)",
				"adapter": knownAdapters[req.AdapterID],
			},
		}, nil
	}

	body, err := json.Marshal(map[string]any{
		"model":       req.Model,
		"messages":    req.Messages,
		"stream":      false,
		"max_tokens":  req.MaxTokens,
		"temperature": req.Temperature,
		"top_p":       req.TopP,
	})
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, mlcURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 600 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("mlc proxy: %w", err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("mlc status %d: %s", resp.StatusCode, truncate(string(raw), 400))
	}

	var parsed struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
		Usage map[string]int `json:"usage"`
	}
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return nil, fmt.Errorf("mlc json: %w", err)
	}

	content := ""
	if len(parsed.Choices) > 0 {
		content = parsed.Choices[0].Message.Content
	}

	return &RichResult{
		Content:   content,
		AdapterID: req.AdapterID,
		Model:     req.Model,
		Usage:     parsed.Usage,
		Meta: map[string]string{
			"status":  "ok",
			"adapter": knownAdapters[req.AdapterID],
		},
	}, nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
