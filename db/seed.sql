-- Demonstraciniai duomenys (N-16: >=3-5 irasai kiekvienoje lenteleje).
-- Kiekviena komanda dalis papildo savo lenteles zemiau esanciame skyriuje.

-- === Core: users ===
-- Slaptazodis visiems demo naudotojams: "Slaptazodis123" (hash sugeneruotas su werkzeug.security.generate_password_hash)
INSERT INTO users (name, email, password_hash, ai_consent) VALUES
    ('Jonas Jonaitis', 'jonas.jonaitis@example.com', 'pbkdf2:sha256:600000$placeholder$replace_me_1', TRUE),
    ('Ona Onaite', 'ona.onaite@example.com', 'pbkdf2:sha256:600000$placeholder$replace_me_2', TRUE),
    ('Petras Petraitis', 'petras.petraitis@example.com', 'pbkdf2:sha256:600000$placeholder$replace_me_3', FALSE);

-- === AK (auth) skyrius: papildomu seed irasu auth komponentui nereikia, naudoja users lentele. ===

-- === TVK/AA skyrius (tvarkarascio importas ir atpazinimas): ===
-- TODO (teammate slice): INSERT INTO pdf_documents / schedules / subjects / study_events ...

-- === DVK skyrius (darbo valandos): ===
-- TODO (teammate slice): INSERT INTO workplaces / work_shifts ...

-- === KVK/AN skyrius (konfliktai): ===
-- TODO (teammate slice): INSERT INTO conflicts / notifications / ai_requests ...
