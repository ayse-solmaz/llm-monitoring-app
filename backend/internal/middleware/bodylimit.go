package middleware

import (
	"net/http"

	"github.com/aysnu/llm-monitoring-app/backend/internal/response"
	"github.com/gin-gonic/gin"
)

const defaultMaxBodyBytes = 1 << 20 // 1 MB

func MaxBodySize(maxBytes int64) gin.HandlerFunc {
	if maxBytes <= 0 {
		maxBytes = defaultMaxBodyBytes
	}

	return func(c *gin.Context) {
		if c.Request.ContentLength > maxBytes {
			response.PayloadTooLarge(c, "request body too large")
			c.Abort()
			return
		}

		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxBytes)
		c.Next()
	}
}
