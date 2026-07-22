package response

import (
	"encoding/json"
	"net/http"
)

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type envelope struct {
	Data  any       `json:"data"`
	Error *apiError `json:"error"`
}

func EnvelopeOK(w http.ResponseWriter, data any) {
	JSON(w, http.StatusOK, envelope{Data: data, Error: nil})
}

func EnvelopeCreated(w http.ResponseWriter, data any) {
	JSON(w, http.StatusCreated, envelope{Data: data, Error: nil})
}

func EnvelopeError(w http.ResponseWriter, status int, code, message string) {
	JSON(w, status, envelope{
		Data:  nil,
		Error: &apiError{Code: code, Message: message},
	})
}

func EnvelopeBadRequest(w http.ResponseWriter, message string) {
	EnvelopeError(w, http.StatusBadRequest, "bad_request", message)
}

func EnvelopeUnauthorized(w http.ResponseWriter, message string) {
	EnvelopeError(w, http.StatusUnauthorized, "unauthorized", message)
}

func EnvelopeNotFound(w http.ResponseWriter, message string) {
	EnvelopeError(w, http.StatusNotFound, "not_found", message)
}

func EnvelopeConflict(w http.ResponseWriter, message string) {
	EnvelopeError(w, http.StatusConflict, "conflict", message)
}

func EnvelopeInternal(w http.ResponseWriter, message string) {
	EnvelopeError(w, http.StatusInternalServerError, "internal_error", message)
}

func RawJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
