# 1 sprinto užduočių paskirstymas

Pagrindas (`main`): domain sluoksnis, application ports, config/DB/Gemini klientas, bendri
Flask komponentai, DB schema, Docker. Žemiau - 4 funkcijos (feature), kiekviena savo šakoje.
Kiekvienas narys paima savo šaką, peržiūri kodą ir **pats** daro `git commit`/`push` bei PR į `main`.

Šakų pavadinimai: `feature/auth`, `feature/work-shifts`, `feature/schedule-import`,
`feature/conflicts-and-week-view`. Šakos nepriklauso viena nuo kitos, galima sulieti bet kokia tvarka
(sujungimo taškai: `app/container.py`, `app/web/__init__.py`, `app/web/templates/base.html`,
`index.html` - kiekviena šaka keičia tik savo pažymėtą vietą).

Taisyklės visiems:
- Servisai (`application/`) nežino apie Flask, SQL ar Gemini - tik apie `ports.py` sąsajas.
- SQL tik `infrastructure/persistence/`, Gemini tik `infrastructure/ai/` (N-02).
- Naudotojui rodomi tekstai - lietuviškai, `web/messages.py` (servisai grąžina klaidų kodus).
- Slaptažodžiai/API raktai tik `.env` (N-22). Testai: `python -m pytest`.

Specifikacijos žymėjimai: US-xx naudotojų istorijos, F-xx funkciniai, N-xx nefunkciniai reikalavimai.

---

## 1. `feature/auth` - registracija ir prisijungimas
US-01 | F-01, F-02 | N-20, N-21

Failai: `application/auth_service.py`, `infrastructure/security.py`,
`infrastructure/persistence/user_repository.py`, `web/auth/`, `templates/login.html`, `register.html`,
`tests/test_auth.py`.

- Registracija: vardas, el. paštas (unikalus), slaptažodis >= 8 simboliai; saugoma tik slaptažodžio santrauka.
- Prisijungimas: bendras pranešimas "Neteisingas el. paštas arba slaptažodis"; atsijungimas baigia sesiją.
- Kitos funkcijos naudoja `web/context.py::login_required`.

## 2. `feature/work-shifts` - darbo valandos
US-04 | F-09, F-10 | N-13

Failai: `application/work_shift_service.py`, `web/work_shifts/`, `templates/shifts.html`,
`tests/test_work_shifts.py`. (`PostgresWorkShiftRepository` yra `main`.)

- Forma: darbovietė, savaitės diena, pradžia/pabaiga (HH:MM); pabaiga turi būti vėlesnė už pradžią.
- Sąrašas ir šalinimas; šalinti galima tik savo pamainas (N-21).
- Po pakeitimo servisas iškviečia `ChangeNotifier` (F-12) - konfliktų funkcija užsiprenumeruoja.

## 3. `feature/schedule-import` - PDF importas ir atpažinimas
US-02, US-03 | F-03..F-08 | N-03, N-04, N-08, N-10, N-23, N-24

Failai: `application/schedule_import_service.py`, `infrastructure/ai/gemini_schedule_recognizer.py`,
`infrastructure/persistence/pdf_document_repository.py`, `web/schedule/`, `templates/upload.html`,
`review.html`, `tests/test_schedule_import.py`.

- Įkėlimas: tik PDF, <= 10 MB, privalomas sutikimas siųsti DI tiekėjui.
- Gemini atpažinimas, iki 3 bandymų, atsakymo struktūros tikrinimas; nesėkmė -> būsena KLAIDA.
- Peržiūros lentelė su laukų tikrinimu; išsaugoma tik po "Patvirtinti" (N-24).

## 4. `feature/conflicts-and-week-view` - konfliktai ir savaitės vaizdas
US-05, US-06, US-07 | F-11..F-16 | N-09, N-11, N-12

Failai: `application/conflict_service.py`, `application/week_view_service.py`,
`infrastructure/ai/gemini_conflict_analyzer.py`, `infrastructure/persistence/conflict_repository.py`,
`notification_repository.py`, `web/week/`, `templates/week_view.html`, `tests/test_conflicts_and_week.py`.

- Savaitės vaizdas (pirmadienio data YYYY-MM-DD), konfliktai pažymimi spalva ir tekstu.
- Konfliktų paieška automatiškai po tvarkaraščio/pamainų pakeitimo; DI rezultatas tikrinamas
  `domain/overlap.py` taisykle (besiliečiantys intervalai - ne konfliktas).
- Pranešimai apie naujus konfliktus; DI klaida nesustabdo sistemos (N-11).

---

## Integravimas
Sulietus visas šakas: `tests/test_full_flow.py` tikrina visą scenarijų; patikrinti `db/seed.sql`
(N-16) ir pereiti scenarijų naršyklėje (`task`, tada http://127.0.0.1:5000).
