# Tvarkarastis

Studentu tvarkaraščių planavimo asistentas - 1 sprinto prototipas.
Pilna specifikacija: žr. komandos Word dokumentą (ISPK ... 1sprintas).

## Architektūra (1 sprintas)

Komponentai pagal Coad-Yourdon modelį: **GVS** (interfeisas), **AK** (autentifikacija),
**TVK** (tvarkaraščių valdymas + importas), **AA** (DI atpažinimo agentas), **DVK**
(darbo valandų valdymas), **KVK** (konfliktų valdymas), **AN** (DI analizės agentas),
**DPK** (duomenų prieiga - **vienintelis** komponentas, kalbantis su DB), **DB** (PostgreSQL).

Sistema veikia lokaliai: naršyklė + Python (Flask) + PostgreSQL vienu kompiuteriu.
Internetu pasiekiamas tik Google Gemini API (AA ir AN komponentai).

## Projekto struktūra

```
app/
  config.py          - konfigūracijos skaitymas (config.ini)
  dpk/db.py          - vienintelė vieta, kuri kalba su PostgreSQL
  gvs/               - bendri šablonai (base.html), CSS, pagrindinis "/" maršrutas
  ak/                - (priduodama) registracija/prisijungimas
  tvk/                - (priduodama) PDF importas + savaitės vaizdas
  aa/                - (priduodama) atpažinimo DI agentas
  dvk/                - (priduodama) darbo valandos
  kvk/, an/          - (priduodama) konfliktų aptikimas
db/
  schema.sql         - DB schema (vykdyti pirmą)
  seed.sql           - demo duomenys (N-16)
docs/
  sprint1_assignments.md - kas konkrečiai turi padaryti kiekvienas komandos narys
```

## Paleidimas lokaliai

1. Python 3.11+, PostgreSQL 14+ turi būti įdiegti.
2. `python -m venv .venv && .venv\Scripts\activate` (Windows) tada `pip install -r requirements.txt`.
3. Sukurti DB: `createdb tvarkarastis` (arba per pgAdmin), tada:
   ```
   psql -d tvarkarastis -f db/schema.sql
   psql -d tvarkarastis -f db/seed.sql
   ```
4. `copy config.example.ini config.ini` ir užpildyti DB prisijungimo duomenis + Gemini API raktą.
   **config.ini niekada necommitinamas** (yra .gitignore, žr. N-22).
5. `python run.py` - atidaryti http://127.0.0.1:5000

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

Taisyklė: komponentai, kurie nėra DPK, **neatidaro** savo psycopg2 jungčių - visa DB
prieiga eina per `app/dpk/db.py` arba per repository funkcijas, kurias kiekviena dalis
pati prisideda ten pagal savo lenteles.
