package models

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

type Session struct {
	ID          uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	UserID      uuid.UUID `gorm:"type:uuid;not null;index" json:"user_id"`
	ModelID     string    `gorm:"not null" json:"model_id"`
	DeviceInfo  string    `json:"device_info"`
	ModelLoadMs *int64    `json:"model_load_ms"`
	CreatedAt   time.Time `json:"created_at"`
	Messages    []Message `gorm:"foreignKey:SessionID;constraint:OnDelete:CASCADE" json:"messages,omitempty"`
}

func (Session) TableName() string {
	return "sessions"
}

func (s *Session) BeforeCreate(_ *gorm.DB) error {
	if s.ID == uuid.Nil {
		s.ID = uuid.New()
	}
	return nil
}
