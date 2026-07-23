package middleware

import (
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/masterfabric-go/masterfabric/internal/shared/response"
	"golang.org/x/time/rate"
)

const (
	rateLimiterCleanupInterval = 10 * time.Minute
	rateLimiterIdleTTL         = 30 * time.Minute
)

type ipLimiter struct {
	limiter  *rate.Limiter
	lastSeen time.Time
}

// IPRateLimiter tracks per-IP request rates with idle-entry eviction.
type IPRateLimiter struct {
	mu       sync.Mutex
	limiters map[string]*ipLimiter
	r        rate.Limit
	b        int
}

// NewIPRateLimiter creates a limiter allowing requestsPerMinute with the given burst.
func NewIPRateLimiter(requestsPerMinute, burst int) *IPRateLimiter {
	l := &IPRateLimiter{
		limiters: make(map[string]*ipLimiter),
		r:        rate.Limit(float64(requestsPerMinute) / 60.0),
		b:        burst,
	}
	go l.cleanupLoop()
	return l
}

func (l *IPRateLimiter) cleanupLoop() {
	ticker := time.NewTicker(rateLimiterCleanupInterval)
	defer ticker.Stop()

	for range ticker.C {
		cutoff := time.Now().Add(-rateLimiterIdleTTL)
		l.mu.Lock()
		for ip, entry := range l.limiters {
			if entry.lastSeen.Before(cutoff) {
				delete(l.limiters, ip)
			}
		}
		l.mu.Unlock()
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

// Middleware returns Chi-compatible middleware that enforces the IP rate limit.
func (l *IPRateLimiter) Middleware() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ip := clientIP(r)
			if !l.getLimiter(ip).Allow() {
				response.EnvelopeTooManyRequests(w, "rate limit exceeded")
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RateLimitAuth limits auth endpoints to 10 requests/minute per IP (burst 10).
func RateLimitAuth() func(http.Handler) http.Handler {
	return authRateLimiter.Middleware()
}

var authRateLimiter = NewIPRateLimiter(10, 10)

func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		parts := strings.Split(xff, ",")
		if ip := strings.TrimSpace(parts[0]); ip != "" {
			return ip
		}
	}
	if xrip := strings.TrimSpace(r.Header.Get("X-Real-IP")); xrip != "" {
		return xrip
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		if r.RemoteAddr != "" {
			return r.RemoteAddr
		}
		return "unknown"
	}
	return host
}
