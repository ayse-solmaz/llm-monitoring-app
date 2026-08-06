-- +goose Up
-- Singleton row for FINAL BOSS soft-adapter / DeepKwiki admin settings.
CREATE TABLE IF NOT EXISTS llm_admin_settings (
    id                  SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    system_prompt       TEXT NOT NULL,
    temperature         DOUBLE PRECISION NOT NULL DEFAULT 0,
    top_p               DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    max_tokens          INT NOT NULL DEFAULT 48,
    adapter_id          VARCHAR(64) NOT NULL DEFAULT '',
    deep_kwiki_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by          UUID REFERENCES users(id) ON DELETE SET NULL
);

INSERT INTO llm_admin_settings (
    id,
    system_prompt,
    temperature,
    top_p,
    max_tokens,
    adapter_id,
    deep_kwiki_enabled
) VALUES (
    1,
    'Answer briefly and accurately. Prefer Turkish when the user writes Turkish.',
    0,
    0.9,
    48,
    '',
    TRUE
) ON CONFLICT (id) DO NOTHING;

-- +goose Down
DROP TABLE IF EXISTS llm_admin_settings;
