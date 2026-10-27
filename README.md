# Tvarkarastis

Studentu tvarkaraščių planavimo asistentas - 1 sprinto prototipas.
Pilna specifikacija: žr. komandos Word dokumentą (ISPK ... 1sprintas).

## Architektūra (Clean Architecture)

Kodas skirstomas į sluoksnius; priklausomybės eina tik į vidų (`web` → `application` → `domain`).
`infrastructure` įgyvendina `application` sluoksnio sąsajas (ports), todėl DB ar DI tiekėją galima
pakeisti nekeičiant verslo logikos (N-18, N-19).

Schedule-import done

```
app/
  domain/           verslo esybės ir taisyklės (be Flask/DB/DI): entities, weekday, overlap
  application/      use case servisai (klasės) ir ports (Protocol sąsajos): auth_service,
                    schedule_import_service, work_shift_service, conflict_service, week_view_service
  infrastructure/   adapteriai: config, database, persistence/ (PostgreSQL), ai/ (Gemini), security
  web/              Flask: auth/, schedule/, work_shifts/, week/ (routes), templates/, static/
  container.py      composition root - čia surišami servisai su adapteriais
db/                 schema.sql, seed.sql
tests/              pytest; servisai testuojami su in-memory fake'ais (tests/fakes.py)
docs/               komandos užduočių paskirstymas
```

Specifikacijos komponentai (Coad-Yourdon) -> kodas:

| Specifikacija | Kur kode |
|---|---|
| GVS (interfeisas) | `app/web/` |
| AK (autentifikacija) | `application/auth_service.py`, `web/auth/`, `infrastructure/security.py` |
| TVK (tvarkaraščių importas) | `application/schedule_import_service.py`, `web/schedule/` |
| TVK (savaitės vaizdas) | `application/week_view_service.py`, `web/week/` |
| DVK (darbo valandos) | `application/work_shift_service.py`, `web/work_shifts/` |
| KVK (konfliktai) | `application/conflict_service.py`, `domain/overlap.py` |
| AA (atpažinimo DI agentas) | `infrastructure/ai/gemini_schedule_recognizer.py` |
| AN (analizės DI agentas) | `infrastructure/ai/gemini_conflict_analyzer.py` |
| DPK + DB (duomenų prieiga) | `infrastructure/database.py`, `infrastructure/persistence/` |

Sistema veikia lokaliai: naršyklė + Python (Flask) + PostgreSQL vienu kompiuteriu.
Internetu pasiekiamas tik Google Gemini API.

## Paleidimas (Docker + Task) - rekomenduojama

Reikia: Docker Desktop ir [Task](https://taskfile.dev) (`winget install Task.Task`).

```
copy .env.example .env      # tada .env uzpildyti (GEMINI_API_KEY, slaptazodzius)
task                        # sukuria DB (schema), paleidzia app -> http://127.0.0.1:5000
```

Kitos komandos: `task down` (sustabdyti), `task reset` (istrinti DB), `task logs`,
`task seed` (demo duomenys), `task psql`. `.env` niekada nekomitinamas (N-22).
Gemini API raktas imamas is `.env` (`GEMINI_API_KEY`).

## Paleidimas be Docker

1. Python 3.11+, PostgreSQL 14+; `python -m venv .venv`, `pip install -r requirements.txt`.
2. `createdb tvarkarastis`, tada `psql -d tvarkarastis -f db/schema.sql` (+ `db/seed.sql`).
3. `.env` (su `DB_HOST=localhost`) arba `config.ini` is `config.example.ini`.
4. `python run.py` - http://127.0.0.1:5000

Testai: `pip install -r requirements-dev.txt`, tada `python -m pytest`.

## Darbo eiga komandai

Kiekvienas komandos narys dirba savo "feature" šakoje (žr. `docs/sprint1_assignments.md`),
naudojasi AI (Claude) kodui generuoti/taisyti, bet **patys** peržiūri ir `git commit`/`push`
savo dalį iš savo GitHub paskyros, tada atidaro Pull Request į `main`.

```
git checkout -b feature/<tavo-dalis>
... (kodas) ...
git add <failai>
git commit -m "..."
git push -u origin feature/<tavo-dalis>
```

Taisyklė: SQL rašomas tik `app/infrastructure/persistence/`, o servisai (`app/application/`) priklauso
tik nuo `ports.py` sąsajų (žr. `docs/sprint1_assignments.md`).
