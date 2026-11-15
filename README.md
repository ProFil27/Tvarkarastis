# Tvarkarastis

Studentu tvarkaraščių planavimo asistentas - 2 sprinto prototipas (duomenų redagavimas ir Google Calendar sinchronizavimas).
Pilna specifikacija: žr. komandos Word dokumentą (ISPK ... 2sprintas).

## Architektūra 

Kodas skirstomas į sluoksnius; priklausomybės eina tik į vidų (`web` → `application` → `domain`).
`infrastructure` įgyvendina `application` sluoksnio sąsajas (ports), todėl DB ar DI tiekėją galima
pakeisti nekeičiant verslo logikos (N-18, N-19).

Schedule-import done

```
app/
  domain/           verslo esybės ir taisyklės (be Flask/DB/DI): entities, weekday, overlap
  application/      use case servisai (klasės) ir ports (Protocol sąsajos): auth_service,
                    schedule_import_service, study_event_service, work_shift_service, conflict_service,
                    week_view_service, reminder_service, calendar_sync_service
  infrastructure/   adapteriai: config, database, persistence/ (PostgreSQL), ai/ (Gemini / Claude),
                    calendar/ (Google Calendar), security (slaptažodžiai, žetonų šifravimas)
  web/              Flask: auth/, schedule/, study_events/, work_shifts/, week/, reminders/, calendar/ (routes),
                    templates/, static/
  container.py      composition root - čia surišami servisai su adapteriais
db/                 schema.sql, seed.sql, migrations/ (esamoms duomenų bazėms: 002_... - 010_...)
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
| TVK (paskaitų redagavimas, tvarkaraščio keitimas) | `application/study_event_service.py`, `application/event_rows.py`, `web/study_events/` |
| DVK (darbo valandos) | `application/work_shift_service.py`, `web/work_shifts/` |
| PK (priminimai) | `application/reminder_service.py`, `domain/reminder.py`, `web/reminders/` |
| KSK (kalendoriaus sinchronizavimas) | `application/calendar_sync_service.py`, `application/calendar_events.py`, `web/calendar/` |
| GKK (Google Calendar sąsaja) | `infrastructure/calendar/google_calendar_client.py` (vienintelis kreipiasi į Google) |
| KVK (konfliktai) | `application/conflict_service.py`, `domain/overlap.py` |
| AA (atpažinimo DI agentas) | `infrastructure/ai/gemini_schedule_recognizer.py` |
| AN (analizės DI agentas) | `infrastructure/ai/gemini_conflict_analyzer.py` |
| DPK + DB (duomenų prieiga) | `infrastructure/database.py`, `infrastructure/persistence/` |

Sistema veikia lokaliai: naršyklė + Python (Flask) + PostgreSQL vienu kompiuteriu.
Internetu pasiekiamas pasirinkto tiekėjo API (Google Gemini arba Anthropic Claude) ir Google Calendar API
(OAuth 2.0 prieigos patvirtinimas; naršyklė grįžta į `http://127.0.0.1:5000/calendar/callback`).

### 2 sprinto naujienos

- **Paskaitų redagavimas** (langas „Paskaitos“) ir darbo pamainų keitimas; po kiekvieno pakeitimo konfliktai ieškomi iš naujo.
- **1 / 2 savaitės paskaitos**: kai kurios paskaitos vyksta tik 1 arba tik 2 savaitę. 1 savaitė - savaitė (pirmadienis-sekmadienis),
  kurioje yra rugsėjo 1 d.; toliau savaitės kaitaliojasi be pertraukos (pavasario semestre skaičiavimas nepradedamas iš naujo).
  Eksportuojant į Google Calendar tokios paskaitos kartojamos kas antrą savaitę (`RRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL=...`).
- **Priminimai** įkelti atnaujintą tvarkaraštį pirmąsias 7 semestro / mėnesio dienas (`SEMESTER_START_DATES`).
- **Naujo tvarkaraščio įkėlimas vietoje seno** (žymeklis „Pakeisti esamą tvarkaraštį“ + patvirtinimas).
- **Google Calendar**: prijungimas, eksportas, automatinis atnaujinimas po pakeitimų, sinchronizavimo būsena ir klaidos.
- **Pamainų serija**: „Kartoti kas savaitę iki“ sukuria vieną serijos įrašą (kiekviena diena lieka atskira pamaina). Seriją galima
  keisti ar šalinti visą arba keisti tik vieną dieną (ji tampa „Išimtimi“); į Google Calendar eksportuojamas vienas
  pasikartojantis įvykis (`RRULE` + `EXDATE` praleistoms savaitėms). Po pakeitimų Google atnaujinamas fone.
- Darbo pamaina turi konkrečią **datą** (YYYY-MM-DD), todėl eksportuojama kaip pavienis įvykis.
- Laiko laukai - tekstiniai (`930` -> `09:30`, rodyklės keičia laiką), be naršyklės laikrodžio.

## Paleidimas (Docker + Task) - rekomenduojama

Reikia: Docker Desktop ir [Task](https://taskfile.dev) (`winget install Task.Task`).

```
copy .env.example .env      # tada .env uzpildyti (AI_PROVIDER, pasirinkto tiekėjo API raktą ir slaptazodzius)
task                        # sukuria DB (schema), paleidzia app -> http://127.0.0.1:5000
```

Kitos komandos: `task down` (sustabdyti), `task reset` (istrinti DB), `task logs`,
`task seed` (demo duomenys), `task psql`, `task migrate` (esamai DB pritaikyti `db/migrations/*.sql`; nauja DB
jau gauna pilną `db/schema.sql`). `.env` niekada nekomitinamas (N-22).
Laikas rodomas ir siunčiamas į kalendorių Lietuvos laiku (`Europe/Vilnius`) nepriklausomai nuo kompiuterio laiko juostos.
AI tiekėją nustato `.env` kintamasis `AI_PROVIDER`: `gemini` (numatytasis) arba `claude`.
Užpildykite atitinkamai `GEMINI_API_KEY` arba `CLAUDE_API_KEY`; modelius galima pasirinkti
per `GEMINI_MODEL` ir `CLAUDE_MODEL`. API užklausos klaidos bandomos dar kartą su eksponentine
pertrauka; jei tiekėjas pateikia `Retry-After`, laukiama bent nurodytą laiką.

## Google Calendar nustatymas (N-38)

Be šių nustatymų sistema veikia, tik kalendoriaus lange rodomas pranešimas, kad integracija nesukonfigūruota.

1. [Google Cloud Console](https://console.cloud.google.com/) sukurkite projektą (pvz., „Tvarkarastis“).
2. **APIs & Services -> Library**: įjunkite **Google Calendar API**.
3. **APIs & Services -> OAuth consent screen**: tipas **External**, būsena **Testing**; **Test users** sąraše
   pridėkite Google paskyras, kurios naudos sistemą (kol programa netvirtinta, kitų paskyrų Google neleis).
   Scopes: `.../auth/calendar.events`, `openid`, `.../auth/userinfo.email` (sistema prašo tik šios minimalios prieigos).
4. **APIs & Services -> Credentials -> Create credentials -> OAuth client ID**: tipas **Web application**;
   **Authorized redirect URIs**: `http://127.0.0.1:5000/calendar/callback` (tiksliai taip, su `127.0.0.1`, ne `localhost`).
5. Nukopijuokite **Client ID** ir **Client secret** į `.env`:
   ```
   GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/calendar/callback
   TOKEN_ENCRYPTION_KEY=<žr. toliau>
   ```
6. Sugeneruokite žetonų šifravimo raktą (jis saugomas tik `.env`, duomenų bazėje žetonai yra užšifruoti):
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
7. Paleiskite iš naujo (`task down`, `task`), atidarykite **Kalendorius**, pažymėkite sutikimą, spauskite
   **Prijungti Google Calendar**, patvirtinkite prieigą ir spauskite **Eksportuoti į Google Calendar**.

Pastabos: sistema keičia ir šalina tik pati sukurtus įvykius (jų Google identifikatoriai saugomi); jei prieigos žetonas
nebegalioja, rodoma būsena „Reikia prisijungti iš naujo“. Pakeitus `TOKEN_ENCRYPTION_KEY` anksčiau prijungtas paskyras reikės prijungti iš naujo.

## Paleidimas be Docker

1. Python 3.11+, PostgreSQL 14+; `python -m venv .venv`, `pip install -r requirements.txt`.
2. `createdb tvarkarastis`, tada `psql -d tvarkarastis -f db/schema.sql` (+ `db/seed.sql`).
   Jau turimai 1 sprinto duomenų bazei: `psql -d tvarkarastis -f db/migrations/002_shift_date.sql` ir toliau iš eilės
   visi `db/migrations/*.sql` (jie kartojami saugiai).
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
