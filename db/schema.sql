-- Tvarkarastis - PostgreSQL schema (sprint 1)
-- Class diagram: User, Schedule, Subject, StudyEvent, Workplace, WorkShift,
-- PdfDocument, AiRequest, Conflict, Notification.
-- TimeInterval is a structural class (the week view) and is not stored in a table.
-- Enum values are the ASCII domain terms defined in the specification.

CREATE TYPE study_event_type AS ENUM ('PASKAITA', 'PRATYBOS', 'LABORATORINIS_DARBAS');

CREATE TYPE weekday AS ENUM (
    'PIRMADIENIS', 'ANTRADIENIS', 'TRECIADIENIS', 'KETVIRTADIENIS',
    'PENKTADIENIS', 'SESTADIENIS', 'SEKMADIENIS'
);

CREATE TYPE pdf_status AS ENUM ('IKELTAS', 'APDOROJAMAS', 'ATPAZINTAS', 'PATVIRTINTAS', 'KLAIDA');

CREATE TYPE conflict_status AS ENUM ('AKTYVUS', 'IGNORUOTAS', 'ISSPRESTAS');

CREATE TYPE ai_request_type AS ENUM ('ATPAZINIMAS', 'ANALIZE');

-- User: user account (managed by AK)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    ai_consent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

-- PdfDocument: uploaded timetable PDF and its recognition status (TVK/AA)
CREATE TABLE pdf_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    status pdf_status NOT NULL DEFAULT 'IKELTAS',
    uploaded_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Schedule: the user's study schedule with a validity period (TVK)
CREATE TABLE schedules (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pdf_document_id INTEGER REFERENCES pdf_documents(id) ON DELETE SET NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Subject: study subject belonging to a schedule (TVK)
CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL
);

-- StudyEvent: lecture / practical / laboratory session (TVK)
CREATE TABLE study_events (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    event_type study_event_type NOT NULL,
    day_of_week weekday NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    room VARCHAR(100),
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT study_event_time_check CHECK (end_time > start_time)
);

-- Workplace: employer (DVK)
CREATE TABLE workplaces (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL
);

-- WorkShift: working-time interval on a given weekday (DVK)
CREATE TABLE work_shifts (
    id SERIAL PRIMARY KEY,
    workplace_id INTEGER NOT NULL REFERENCES workplaces(id) ON DELETE CASCADE,
    day_of_week weekday NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_changeable BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT work_shift_time_check CHECK (end_time > start_time)
);

-- AiRequest: AI agent request log (AA/AN)
CREATE TABLE ai_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pdf_document_id INTEGER REFERENCES pdf_documents(id) ON DELETE SET NULL,
    request_type ai_request_type NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT now(),
    finished_at TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

-- Conflict: time overlap between a study event and a work shift (KVK/AN)
CREATE TABLE conflicts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    study_event_id INTEGER NOT NULL REFERENCES study_events(id) ON DELETE CASCADE,
    work_shift_id INTEGER NOT NULL REFERENCES work_shifts(id) ON DELETE CASCADE,
    overlap_minutes INTEGER NOT NULL,
    detected_at TIMESTAMP NOT NULL DEFAULT now(),
    status conflict_status NOT NULL DEFAULT 'AKTYVUS'
);

-- Notification: in-system message to the user about a conflict (KVK)
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conflict_id INTEGER REFERENCES conflicts(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    is_read BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_schedules_user_id ON schedules(user_id);
CREATE INDEX idx_study_events_schedule_id ON study_events(schedule_id);
CREATE INDEX idx_work_shifts_workplace_id ON work_shifts(workplace_id);
CREATE INDEX idx_conflicts_user_id ON conflicts(user_id);
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
