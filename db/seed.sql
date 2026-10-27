-- Demo data (N-16: at least 3-5 rows in every table). Intended password of every demo user: "Slaptazodis123".
-- User 1 holds a real VilniusTech timetable (12 events); conflicts and overlaps are computed with the
-- same rule as the application (touching intervals are not conflicts).

INSERT INTO users (id, name, email, password_hash, ai_consent) VALUES
    (1, 'Jonas Jonaitis', 'jonas.jonaitis@example.com', 'scrypt:32768:8:1$mrUlj5ne1scZDcsQ$7c402d08ae0db97f144660311ba5f4c0a78521cb12074c2bf2da24ad9665b1eba62fede766d47e58fb79f89a4e2af5210ffc6e4951c0cf05731407ae9f3b06fe', TRUE),
    (2, 'Ona Onaitė', 'ona.onaite@example.com', 'scrypt:32768:8:1$xoVtomIdlP0F9vrf$3a1bd8655a34aeedb03f9e08a8e8483af051ad7412ceb7f745794178cf882b2b1fff27d15a04f8892604e9a9924d7204b8815d8e5633131db66a78cb4991255d', TRUE),
    (3, 'Petras Petraitis', 'petras.petraitis@example.com', 'scrypt:32768:8:1$ZY4l9MfKf8PCUWyk$c4e9fb18be07c9a75f08f53fd99d2d18535be15b3bd8d7018e24fc45014245ca02b2ce00dd1d9d797693b5b4603421ec94545472693a176404db75cfdea03995', FALSE);

INSERT INTO pdf_documents (id, user_id, filename, status) VALUES
    (1, 1, 'timetable_2026-10-27.pdf', 'PATVIRTINTAS'),
    (2, 2, 'ona_tvarkarastis.pdf', 'PATVIRTINTAS'),
    (3, 3, 'petras_tvarkarastis.pdf', 'PATVIRTINTAS'),
    (4, 3, 'neteisingas_failas.pdf', 'KLAIDA');

INSERT INTO schedules (id, user_id, pdf_document_id, valid_from, valid_to) VALUES
    (1, 1, 1, '2026-09-01', '2026-12-20'),
    (2, 2, 2, '2026-09-01', '2026-12-20'),
    (3, 3, 3, '2026-09-01', '2026-12-20');

INSERT INTO subjects (id, schedule_id, name) VALUES
    (1, 1, 'Debesų kompiuterija'),
    (2, 1, 'Programų sistemų kokybė'),
    (3, 1, 'Informatikos teisė'),
    (4, 1, 'Specialybės kalbos kultūra'),
    (5, 1, 'Informacinės sistemos programų kūrimas'),
    (6, 1, 'Išmaniųjų įrenginių programavimas'),
    (7, 2, 'Duomenų bazės'),
    (8, 2, 'Algoritmai'),
    (9, 2, 'Anglų kalba'),
    (10, 3, 'Matematika'),
    (11, 3, 'Fizika'),
    (12, 3, 'Programavimo pagrindai');

INSERT INTO study_events (id, schedule_id, subject_id, event_type, day_of_week, start_time, end_time, room, is_mandatory) VALUES
    (1, 1, 1, 'PRATYBOS', 'PIRMADIENIS', '12:10', '13:45', 'S6(SRL-I) 501', TRUE),
    (2, 1, 1, 'PASKAITA', 'PIRMADIENIS', '14:30', '16:05', 'S2(SRA-I) A02', TRUE),
    (3, 1, 2, 'PASKAITA', 'PIRMADIENIS', '16:20', '17:55', 'S2(SRA-I) A01', TRUE),
    (4, 1, 3, 'PASKAITA', 'ANTRADIENIS', '12:10', '13:45', 'S2(SRA-I) A02', TRUE),
    (5, 1, 3, 'PRATYBOS', 'ANTRADIENIS', '14:30', '16:05', 'S5(SRK-II) 206', TRUE),
    (6, 1, 4, 'PRATYBOS', 'ANTRADIENIS', '14:30', '16:05', 'S5(SRK-II) 206', TRUE),
    (7, 1, 2, 'PRATYBOS', 'ANTRADIENIS', '16:20', '17:55', 'S5(SRK-II) 201', TRUE),
    (8, 1, 5, 'PRATYBOS', 'TRECIADIENIS', '12:10', '13:45', 'S2(SRA-I) A02', TRUE),
    (9, 1, 5, 'PRATYBOS', 'TRECIADIENIS', '14:30', '16:05', 'S2(SRA-I) A02', TRUE),
    (10, 1, 4, 'PASKAITA', 'TRECIADIENIS', '14:30', '16:05', 'S2(SRA-I) A02', TRUE),
    (11, 1, 6, 'PASKAITA', 'KETVIRTADIENIS', '10:20', '11:55', 'S4(SRA-II) A09', TRUE),
    (12, 1, 6, 'LABORATORINIS_DARBAS', 'KETVIRTADIENIS', '12:10', '13:45', 'S6(SRL-I) 427', TRUE),
    (13, 2, 7, 'PASKAITA', 'PIRMADIENIS', '08:30', '10:00', 'SRK-I-401', TRUE),
    (14, 2, 7, 'PRATYBOS', 'ANTRADIENIS', '10:15', '11:45', 'SRK-II-211', TRUE),
    (15, 2, 8, 'PASKAITA', 'TRECIADIENIS', '10:15', '11:45', 'SRK-I-105', TRUE),
    (16, 2, 9, 'PRATYBOS', 'PENKTADIENIS', '12:00', '13:30', 'SRA-II-312', TRUE),
    (17, 3, 10, 'PASKAITA', 'PIRMADIENIS', '10:15', '11:45', 'SRK-I-201', TRUE),
    (18, 3, 11, 'PASKAITA', 'KETVIRTADIENIS', '08:30', '10:00', 'SRK-II-110', TRUE),
    (19, 3, 12, 'LABORATORINIS_DARBAS', 'PENKTADIENIS', '10:15', '11:45', 'SRL-I-214', TRUE);

INSERT INTO workplaces (id, user_id, name) VALUES
    (1, 1, 'Kavinė Rytas'),
    (2, 2, 'UAB Pavyzdys'),
    (3, 3, 'Sandėlis Vilnius');

INSERT INTO work_shifts (id, workplace_id, day_of_week, start_time, end_time, is_changeable) VALUES
    (1, 1, 'PIRMADIENIS', '15:00', '19:00', FALSE),
    (2, 1, 'TRECIADIENIS', '15:00', '17:00', FALSE),
    (3, 1, 'PENKTADIENIS', '10:00', '14:00', FALSE),
    (4, 2, 'PIRMADIENIS', '09:00', '13:00', FALSE),
    (5, 2, 'TRECIADIENIS', '14:00', '18:00', FALSE),
    (6, 3, 'ANTRADIENIS', '08:00', '12:00', FALSE);

INSERT INTO ai_requests (id, user_id, pdf_document_id, request_type, started_at, finished_at, attempt_count, error_message) VALUES
    (1, 1, 1, 'ATPAZINIMAS', now(), now(), 1, NULL),
    (2, 2, 2, 'ATPAZINIMAS', now(), now(), 1, NULL),
    (3, 3, 4, 'ATPAZINIMAS', now(), now(), 3, 'Recognition failed after 3 attempts: 503 UNAVAILABLE (model under high demand)'),
    (4, 1, NULL, 'ANALIZE', now(), now(), 1, NULL),
    (5, 2, NULL, 'ANALIZE', now(), now(), 1, NULL);

INSERT INTO conflicts (id, user_id, study_event_id, work_shift_id, overlap_minutes, status) VALUES
    (1, 1, 2, 1, 65, 'AKTYVUS'),
    (2, 1, 3, 1, 95, 'AKTYVUS'),
    (3, 1, 9, 2, 65, 'AKTYVUS'),
    (4, 1, 10, 2, 65, 'AKTYVUS'),
    (5, 2, 13, 4, 60, 'AKTYVUS');

INSERT INTO notifications (id, user_id, conflict_id, message, is_read) VALUES
    (1, 1, 1, 'Aptiktas konfliktas: pirmadienis 14:30–16:05', TRUE),
    (2, 1, 2, 'Aptiktas konfliktas: pirmadienis 16:20–17:55', FALSE),
    (3, 1, 3, 'Aptiktas konfliktas: trečiadienis 14:30–16:05', FALSE),
    (4, 1, 4, 'Aptiktas konfliktas: trečiadienis 14:30–16:05', FALSE),
    (5, 2, 5, 'Aptiktas konfliktas: pirmadienis 08:30–10:00', FALSE);

-- Keep the serial sequences ahead of the explicit ids above.
SELECT setval(pg_get_serial_sequence('users', 'id'), 3);
SELECT setval(pg_get_serial_sequence('pdf_documents', 'id'), 4);
SELECT setval(pg_get_serial_sequence('schedules', 'id'), 3);
SELECT setval(pg_get_serial_sequence('subjects', 'id'), 12);
SELECT setval(pg_get_serial_sequence('study_events', 'id'), 19);
SELECT setval(pg_get_serial_sequence('workplaces', 'id'), 3);
SELECT setval(pg_get_serial_sequence('work_shifts', 'id'), 6);
SELECT setval(pg_get_serial_sequence('ai_requests', 'id'), 5);
SELECT setval(pg_get_serial_sequence('conflicts', 'id'), 5);
SELECT setval(pg_get_serial_sequence('notifications', 'id'), 5);
