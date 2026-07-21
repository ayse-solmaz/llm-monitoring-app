package models

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

const (
	DecisionAccept = "accept"
	DecisionReview = "review"
	DecisionReject = "reject"
)

type Score struct {
	ID           uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	MessageID    uuid.UUID `gorm:"type:uuid;not null;uniqueIndex" json:"message_id"`
	LatencyScore int       `json:"latency_score"`
	LengthScore  int       `json:"length_score"`
	FormatScore  int       `json:"format_score"`
	Composite    int       `json:"composite"`
	Decision     string    `gorm:"not null" json:"decision"`
	CreatedAt    time.Time `json:"created_at"`
}

func (Score) TableName() string {
	return "scores"
}

func (s *Score) BeforeCreate(_ *gorm.DB) error {
	if s.ID == uuid.Nil {
		s.ID = uuid.New()
	}
	return nil
}

func ValidDecision(decision string) bool {
	switch decision {
	case DecisionAccept, DecisionReview, DecisionReject:
		return true
	default:
		return false
	}
}
