CREATE TABLE IF NOT EXISTS candidate_application (
    id             BIGSERIAL PRIMARY KEY,
    name           TEXT        NOT NULL,
    email          TEXT        NOT NULL,
    position       TEXT        NOT NULL,
    resume_key     TEXT        NOT NULL,
    resume_preview TEXT,
    submitted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
