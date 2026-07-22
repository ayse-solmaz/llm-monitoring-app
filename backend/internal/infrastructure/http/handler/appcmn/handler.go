package appcmn

import (
	"net/http"
	"os"

	"github.com/masterfabric-go/masterfabric/internal/shared/response"
)

type Handler struct {
	version string
	commit  string
}

func NewHandler(version, commit string) *Handler {
	if version == "" {
		version = "0.1.0"
	}
	if commit == "" {
		commit = "dev"
	}
	return &Handler{version: version, commit: commit}
}

func (h *Handler) Healthz(w http.ResponseWriter, _ *http.Request) {
	response.RawJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *Handler) Version(w http.ResponseWriter, _ *http.Request) {
	response.EnvelopeOK(w, map[string]string{
		"version":     h.version,
		"commit_hash": h.commit,
	})
}

func VersionFromEnv() (string, string) {
	v := os.Getenv("BUILD_VERSION")
	c := os.Getenv("GIT_COMMIT")
	return v, c
}
