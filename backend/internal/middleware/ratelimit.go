package middleware

import (
	"sync"
	"time"

	"github.com/aysnu/llm-monitoring-app/backend/internal/response"
	"github.com/gin-gonic/gin"
	"golang.org/x/time/rate"
)

type ipLimiter struct {
	limiter  *rate.Limiter
	lastSeen time.Time
}

type IPRateLimiter struct {
	mu       sync.Mutex
	limiters map[string]*ipLimiter
	r        rate.Limit
	b        int
}

func NewIPRateLimiter(requestsPerMinute, burst int) *IPRateLimiter {
	return &IPRateLimiter{
		limiters: make(map[string]*ipLimiter),
		r:        rate.Limit(float64(requestsPerMinute) / 60.0),
		b:        burst,
	}
}

func (l *IPRateLimiter) getLimiter(ip string) *rate.Limiter {
	l.mu.Lock()
	defer l.mu.Unlock()

	entry, ok := l.limiters[ip]
	if !ok {
		entry = &ipLimiter{
			limiter:  rate.NewLimiter(l.r, l.b),
			lastSeen: time.Now(),
		}
		l.limiters[ip] = entry
	} else {
		entry.lastSeen = time.Now()
	}

	return entry.limiter
}

func (l *IPRateLimiter) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		ip := c.ClientIP()
		if ip == "" {
			ip = "unknown"
		}

		if !l.getLimiter(ip).Allow() {
			response.TooManyRequests(c, "rate limit exceeded")
			c.Abort()
			return
		}

		c.Next()
	}
}

func RateLimitAuth() gin.HandlerFunc {
	return authRateLimiter.Middleware()
}

var authRateLimiter = NewIPRateLimiter(10, 10)
