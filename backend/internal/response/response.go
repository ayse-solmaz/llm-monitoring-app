package response

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

type ErrorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type Envelope struct {
	Data  any        `json:"data"`
	Error *ErrorBody `json:"error"`
}

func JSON(c *gin.Context, status int, data any) {
	c.JSON(status, Envelope{Data: data, Error: nil})
}

func OK(c *gin.Context, data any) {
	JSON(c, http.StatusOK, data)
}

func Created(c *gin.Context, data any) {
	JSON(c, http.StatusCreated, data)
}

func Fail(c *gin.Context, status int, code, message string) {
	c.JSON(status, Envelope{Data: nil, Error: &ErrorBody{Code: code, Message: message}})
}

func BadRequest(c *gin.Context, message string) {
	Fail(c, http.StatusBadRequest, "bad_request", message)
}

func Unauthorized(c *gin.Context, message string) {
	Fail(c, http.StatusUnauthorized, "unauthorized", message)
}

func NotFound(c *gin.Context, message string) {
	Fail(c, http.StatusNotFound, "not_found", message)
}

func Conflict(c *gin.Context, message string) {
	Fail(c, http.StatusConflict, "conflict", message)
}

func InternalError(c *gin.Context, message string) {
	Fail(c, http.StatusInternalServerError, "internal_error", message)
}
