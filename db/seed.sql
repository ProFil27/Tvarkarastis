-- Demo data (N-16: at least 3-5 rows per table).
-- Each component adds seed rows for its own tables in its section below.

-- === Core: users ===
-- Intended password for all demo users: "Slaptazodis123" (hash to be generated with werkzeug.security.generate_password_hash)
INSERT INTO users (name, email, password_hash, ai_consent) VALUES
    ('Jonas Jonaitis', 'jonas.jonaitis@example.com', 'pbkdf2:sha256:600000$placeholder$replace_me_1', TRUE),
    ('Ona Onaite', 'ona.onaite@example.com', 'pbkdf2:sha256:600000$placeholder$replace_me_2', TRUE),
    ('Petras Petraitis', 'petras.petraitis@example.com', 'pbkdf2:sha256:600000$placeholder$replace_me_3', FALSE);

-- === AK (auth) section: no extra rows needed, it only uses the users table. ===

-- === TVK/AA section (schedule import and recognition): ===
-- TODO: INSERT INTO pdf_documents / schedules / subjects / study_events ...

-- === DVK section (work hours): ===
-- TODO: INSERT INTO workplaces / work_shifts ...

-- === KVK/AN section (conflicts): ===
-- TODO: INSERT INTO conflicts / notifications / ai_requests ...
