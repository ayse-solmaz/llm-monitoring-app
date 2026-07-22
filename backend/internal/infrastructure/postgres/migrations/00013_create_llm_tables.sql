-- +goose Up
CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id        VARCHAR(128) NOT NULL,
    device_info     VARCHAR(512) NOT NULL DEFAULT '',
    model_load_ms   BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role                VARCHAR(16) NOT NULL,
    content             TEXT NOT NULL,
    ttft_ms             INT NOT NULL DEFAULT 0,
    tokens_prompt       INT NOT NULL DEFAULT 0,
    tokens_completion   INT NOT NULL DEFAULT 0,
    tokens_per_sec      DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_ms            INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_session_id ON messages(session_id);

CREATE TABLE IF NOT EXISTS scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id      UUID NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
    latency_score   INT NOT NULL,
    length_score    INT NOT NULL,
    format_score    INT NOT NULL,
    composite       INT NOT NULL,
    decision        VARCHAR(16) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scores_message_id ON scores(message_id);

-- +goose Down
DROP TABLE IF EXISTS scores;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS sessions;
