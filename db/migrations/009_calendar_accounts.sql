-- Sprint 2, step 9: the user's connected Google Calendar account (F-24, F-25, N-25, N-43).
-- Tokens are stored encrypted (Fernet); the key is TOKEN_ENCRYPTION_KEY and never reaches the database.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'calendar_account_status') THEN
        CREATE TYPE calendar_account_status AS ENUM ('PRIJUNGTA', 'NEPRIJUNGTA', 'REIKIA_PERPRISIJUNGTI');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS calendar_accounts (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    google_email VARCHAR(255),
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expires_at TIMESTAMP,  -- UTC
    consent_given_at TIMESTAMP,
    connected_at TIMESTAMP,
    status calendar_account_status NOT NULL DEFAULT 'NEPRIJUNGTA'
);
