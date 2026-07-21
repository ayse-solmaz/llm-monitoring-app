package models

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

type Message struct {
	ID                 uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	SessionID          uuid.UUID `gorm:"type:uuid;not null;index" json:"session_id"`
	Role               string    `gorm:"not null" json:"role"`
	Content            string    `gorm:"not null" json:"content"`
	TTFTMs             int       `json:"ttft_ms"`
	TokensPrompt       int       `json:"tokens_prompt"`
	TokensCompletion   int       `json:"tokens_completion"`
	TokensPerSec       float64   `json:"tokens_per_sec"`
	TotalMs            int       `json:"total_ms"`
	CreatedAt          time.Time `json:"created_at"`
	Score              *Score    `gorm:"foreignKey:MessageID;constraint:OnDelete:CASCADE" json:"score,omitempty"`
}

func (Message) TableName() string {
	return "messages"
}

func (m *Message) BeforeCreate(_ *gorm.DB) error {
	if m.ID == uuid.Nil {
		m.ID = uuid.New()
	}
	return nil
}
