package router

import (
	"github.com/aysnu/llm-monitoring-app/backend/internal/config"
	"github.com/aysnu/llm-monitoring-app/backend/internal/handlers"
	"github.com/aysnu/llm-monitoring-app/backend/internal/middleware"
	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

func New(cfg *config.Config, db *gorm.DB) *gin.Engine {
	r := gin.Default()
	r.Use(middleware.CORS(cfg.CORSOrigin))

	cmn := handlers.NewCMNHandler(cfg)
	configHandler := handlers.NewConfigHandler(cfg)
	authHandler := handlers.NewAuthHandler(db, cfg.JWTSecret)
	llmHandler := handlers.NewLLMHandler(db)

	v1 := r.Group("/api/v1")
	{
		v1.GET("/healthz", cmn.Healthz)
		v1.GET("/version", cmn.Version)

		v1.GET("/config", configHandler.GetConfig)
		v1.GET("/config/models", configHandler.GetModels)

		authGroup := v1.Group("/auth")
		authGroup.Use(middleware.MaxBodySize(1 << 20))
		{
			authGroup.POST("/register", middleware.RateLimitAuth(), authHandler.Register)
			authGroup.POST("/login", middleware.RateLimitAuth(), authHandler.Login)
			authGroup.POST("/refresh", authHandler.Refresh)
			authGroup.POST("/logout", authHandler.Logout)

			protected := authGroup.Group("")
			protected.Use(middleware.JWTAuth(cfg.JWTSecret))
			{
				protected.GET("/me", authHandler.Me)
				protected.PUT("/me", authHandler.UpdateMe)
				protected.POST("/change-password", authHandler.ChangePassword)
				protected.DELETE("/me", authHandler.DeleteMe)
			}
		}

		llm := v1.Group("/llm")
		llm.Use(middleware.MaxBodySize(1 << 20))
		llm.Use(middleware.JWTAuth(cfg.JWTSecret))
		{
			llm.POST("/sessions", llmHandler.CreateSession)
			llm.GET("/sessions", llmHandler.ListSessions)
			llm.GET("/sessions/:id", llmHandler.GetSession)
			llm.DELETE("/sessions/:id", llmHandler.DeleteSession)
			llm.POST("/sessions/:id/messages", llmHandler.CreateMessage)
			llm.POST("/sessions/:id/scores", llmHandler.CreateScore)
			llm.GET("/metrics/summary", llmHandler.MetricsSummary)
			llm.GET("/scores/summary", llmHandler.ScoresSummary)
		}
	}

	return r
}
