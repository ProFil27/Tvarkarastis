# 1 sprinto užduočių paskirstymas

Pagrindas (DB schema, Flask karkasas, DPK, bendras GVS šablonas, config) yra `main`
šakoje. Žemiau - 4 lygiavertės dalys likusiems komandos nariams. Kiekvienas kuria
savo `feature/...` šaką, naudojasi Claude kodui rašyti, bet **patys** `commit`/`push`
savo dalį ir atidaro PR į `main`.

Bendros taisyklės visiems:
- DB pasiekiama tik per `app/dpk/db.py` (`get_cursor`) - nerašyti savo psycopg2 jungčių.
- Jinja šablonai paveldi `base.html`; naujus nav-linkus pridėti `app/gvs/templates/base.html`
  komentuotoje vietoje (žr. failą).
- Slaptažodžiai/API raktai - tik `config.ini`, niekada kode (N-22).
- Visi UI tekstai lietuviškai, klaidos raudonos spalvos + tekstas prie lauko (N: pranešimų reik.).

---

## Dalis 1 - AK (autentifikacija)
**Apima:** US-01 | F-01, F-02 | GVS-1, GVS-2 | AK-1, AK-2, AK-3, AK-4 | DPK-1, DPK-2 | N-20
**Šaka:** `feature/ak-auth`
**Nauji failai:** `app/ak/__init__.py`, `app/ak/routes.py`, `app/ak/service.py`,
`app/gvs/templates/register.html`, `app/gvs/templates/login.html`

Ką padaryti:
1. `app/ak/routes.py`: blueprint `ak_bp` su maršrutais `/register` (GET+POST),
   `/login` (GET+POST), `/logout` (POST).
2. Registracija: laukai vardas, el. paštas (unikalus), slaptažodis (>=8 simboliai).
   Slaptažodis saugomas tik kaip `werkzeug.security.generate_password_hash` santrauka (N-20).
   El. pašto unikalumo pažeidimas -> klaida prie lauko.
3. Prisijungimas: patikrinti el. paštą + `check_password_hash`; sėkmės atveju
   `session["user_id"] = ...` ir nukreipimas į savaitės vaizdą (kol jo nėra - į `/`).
   Klaida -> bendras pranešimas "Neteisingas el. paštas arba slaptažodis" (F-02, be detalių,
   kad neatskleistume, kuris laukas klaidingas).
4. Atsijungimas: `session.clear()`.
5. DPK pusėje (`app/dpk/db.py` arba naujas `app/dpk/users.py` naudojant `get_cursor`)
   pridėti: `create_user(name, email, password_hash)`, `get_user_by_email(email)`,
   `get_user_by_id(id)`.
6. Pridėti `@app.before_request`/decorator `login_required`, kurį naudos visos kitos dalys
   (patogu padėti į `app/ak/decorators.py`, kad kitos šakos tik importuotų).
7. `register.html`/`login.html` - formos su klaidų blokais pagal CSS klases `.field-error`/`.invalid`.
8. Atnaujinti `db/seed.sql` savo skiltyje (jei reikia papildomų demo naudotojų).

Priėmimo kriterijai (US-01) - patikrinti rankiniu testavimu prieš PR:
registracija su užimtu el. paštu rodo klaidą; prisijungimas su blogu slaptažodžiu
rodo bendrą klaidą; atsijungus sesija nebeleidžia pasiekti apsaugotų maršrutų.

---

## Dalis 2 - TVK importas + AA (PDF įkėlimas, atpažinimas, peržiūra)
**Apima:** US-02, US-03 | F-03..F-08 | GVS-3, GVS-4, GVS-5, GVS-6 | TVK-1..6 |
AA-1..4 | DPK-3, DPK-4, DPK-5 | N-03, N-04, N-08, N-10, N-23, N-24
**Šaka:** `feature/tvk-aa-import`
**Nauji failai:** `app/tvk/__init__.py`, `app/tvk/import_routes.py`, `app/tvk/service.py`,
`app/aa/__init__.py`, `app/aa/agent.py`, `app/gvs/templates/upload.html`,
`app/gvs/templates/review.html`

Ką padaryti:
1. `app/tvk/import_routes.py`: blueprint `tvk_bp` (prefix `/schedule`), maršrutai
   `/upload` (GET+POST, PDF + sutikimo varnelė), `/review` (GET - rodo atpažintus
   įrašus redaguojamoje lentelėje, POST - `patvirtinti`/`atmesti`).
2. Validacija prieš apdorojimą (TVK-1): tipas PDF, dydis <=10MB (N-03), pažymėtas sutikimas
   (N-23) - be jo failas atmetamas su pranešimu.
3. `app/aa/agent.py` (AA): funkcija `recognize_schedule(pdf_bytes) -> list[dict]`, kuri
   kreipiasi į Gemini API (`google-generativeai`, raktas iš `config.gemini_api_key`) su
   nurodyta JSON struktūra (dalykas, tipas, diena, pradžia, pabaiga, auditorija).
   Nepavykus/klaidinga struktūra - kartoti iki 3 kartų (AA-3), tada grąžinti klaidą (F-05).
4. Struktūros tikrinimas (AA-4) prieš grąžinant TVK - pvz. su `pydantic` arba rankine
   validacija (visi privalomi laukai, pabaiga > pradžia).
5. Peržiūros lentelė (F-06/F-07): kiekvienas laukas redaguojamas; serverio pusėje
   patikrinti privalomus laukus ir `pabaiga > pradžia` prieš išsaugojimą; klaidos rodomos
   prie lauko.
6. Patvirtinus (F-08, TVK-5): sukurti `schedules` įrašą (valid_from/valid_to - einamas
   semestras, nustatyti pagal konfigūruojamą semestro datų konstantą), `subjects` (unikalūs
   pagal pavadinimą tame tvarkaraštyje), `study_events`; `pdf_documents.status = PATVIRTINTAS`.
   Atmetus (TVK-6): duomenys neišsaugomi, atgal į `/upload`.
7. DPK pusėje: `create_pdf_document`, `update_pdf_status`, `create_schedule_with_events`,
   `create_ai_request` / `finish_ai_request` (žurnalas DPK-4, naudoti `ai_requests` lentelę).
8. Atnaujinti `db/seed.sql` savo skiltyje su pavyzdiniu tvarkaraščiu.

Priėmimo kriterijai (US-02/US-03): netinkamo formato/per didelio failo atmetimas su
pranešimu; sėkmingo atpažinimo atveju lentelė redaguojama; klaidingas laukas (pabaiga <
pradžia) parodo klaidą ir neleidžia patvirtinti; "Atmesti" nieko neišsaugo.

---

## Dalis 3 - DVK (darbo valandos)
**Apima:** US-04 | F-09, F-10 | GVS-7 | DVK-1, DVK-2, DVK-3 | DPK-6 | N-13
**Šaka:** `feature/dvk-workhours`
**Nauji failai:** `app/dvk/__init__.py`, `app/dvk/routes.py`, `app/dvk/service.py`,
`app/gvs/templates/shifts.html`

Ką padaryti:
1. `app/dvk/routes.py`: blueprint `dvk_bp` (prefix `/work-shifts`), maršrutai
   `/` (GET - forma + sąrašas), `/add` (POST), `/<id>/remove` (POST).
2. Forma: darbovietė (tekstas - jei darbovietė neegzistuoja naudotojui, sukurti naują
   `workplaces` įrašą), savaitės diena (select iš `weekday` enum reikšmių lietuviškai),
   pradžia/pabaiga (HH:MM, 24 val.).
3. Validacija (DVK-2): privalomi laukai užpildyti, pabaiga > pradžia - klaida prie lauko,
   jei ne.
4. Sąrašas: rodo visas naudotojo pamainas (darbovietė, diena, pradžia-pabaiga) su mygtuku
   "Šalinti".
5. Po sėkmingo išsaugojimo/pašalinimo - paleisti konfliktų paiešką (F-12/DVK-4). Kol KVK
   komponento nėra (jis bus kitoje šakoje), palikti `app/dvk/service.py` su funkcija
   `trigger_conflict_check(user_id)`, kuri *bando* importuoti `app.kvk.service` ir, jei
   modulio dar nėra (`ImportError`), tyliai nieko nedaro (`pass`) - tai leidžia šiai šakai
   veikti nepriklausomai, o integravus KVK dalį veiks automatiškai be papildomų pakeitimų.
6. DPK pusėje: `get_or_create_workplace(user_id, name)`, `create_work_shift(...)`,
   `list_work_shifts(user_id)`, `delete_work_shift(id, user_id)`.
7. Atnaujinti `db/seed.sql` savo skiltyje su pavyzdinėmis darbo pamainomis.

Priėmimo kriterijai (US-04): pamaina su pabaiga < pradžia rodo klaidą; išsaugota pamaina
atsiranda sąraše; pašalinta pamaina sąraše nebelieka.

---

## Dalis 4 - Savaitės vaizdas + KVK + AN (konfliktų aptikimas)
**Apima:** US-05, US-06, US-07 | F-11..F-16 | GVS-8, GVS-9 | TVK-7, TVK-8 | KVK-1..5 |
AN-1, AN-2, AN-3 | DPK-7, DPK-8 | N-09, N-11, N-12
**Šaka:** `feature/kvk-an-conflicts`
**Nauji failai:** `app/tvk/week_routes.py` (atskiras failas nuo importo maršrutų,
kad nebūtų merge konfliktų su Dalimi 2), `app/kvk/__init__.py`, `app/kvk/service.py`,
`app/an/__init__.py`, `app/an/agent.py`, `app/gvs/templates/week_view.html`

Ką padaryti:
1. `app/tvk/week_routes.py`: blueprint `tvk_week_bp` (prefix `/week`), maršrutas
   `/<data>` (pirmadienio data, formatas YYYY-MM-DD) ir `/` (einamoji savaitė).
   Surenka naudotojo `study_events` + `work_shifts` + `conflicts` tai savaitei (TVK-7)
   ir perduoda į `week_view.html` (vienas "TimeInterval" - struktūrinis objektas,
   skaičiuojamas "on the fly", NE DB lentelė).
2. `app/kvk/service.py` (KVK-1): `run_conflict_check(user_id)` - gauna naudotojo
   studijų įvykius ir darbo pamainas per DPK, kreipiasi į AN.
3. `app/an/agent.py` (AN): `detect_conflicts(study_events, work_shifts) -> list[dict]`
   - Gemini API užklausa su suvestu tvarkaraščiu, laukiama JSON struktūra (studijų
     įvykio ID, pamainos ID, sutapimo trukmė min.). Pakartoti iki 3 kartų nepavykus (AN-3).
     Sutapimo trukmė skaičiuojama minutėmis, 1 min. tikslumu; vien besiliečiantys
     intervalai (pabaiga == pradžia) NE konfliktas (N-09).
4. KVK-3: patikrinti AN atsakymo struktūrą, saugoti tik validžius įrašus per DPK.
5. KVK-4/KVK-5: išsaugoti `conflicts` (status=AKTYVUS), sukurti `notifications` įrašą
   kiekvienam naujam konfliktui (tekstas pvz. "Aptiktas konfliktas: pirmadienis 09:00-10:00").
6. `week_view.html`: savaitės lentelė (7 dienos), paskaitos ir pamainos; konfliktuojantys
   įrašai pažymimi CSS klase `.conflict` + tekstinė žymė `.conflict-label` ("Konfliktas"),
   kitaip `.status-ok` ("OK"); paspaudus konfliktą - detalės (paskaita, pamaina, trukmė).
   Naršymas tarp savaičių (ankstesnė/kita) - URL `/week/<date>`.
7. DPK pusėje: `list_study_events_and_shifts_for_week(user_id, week_start)`,
   `save_conflicts(...)`, `create_notification(...)`, `list_notifications(user_id)`.
8. Performanso reikalavimas N-12: visa konfliktų paieška (su DI užklausa) <=2 min.
9. Atnaujinti `db/seed.sql` savo skiltyje su pavyzdiniais konfliktais/pranešimais.

Priėmimo kriterijai (US-05/06/07): savaitės vaizdas rodo paskaitas+pamainas+OK/Konfliktas
būseną; po naujos pamainos/tvarkaraščio išsaugojimo konfliktų paieška paleidžiama
automatiškai; naujas konfliktas sukuria pranešimą; besiliečiantys (ne persidengiantys)
intervalai nelaikomi konfliktu.

---

## Integravimas (visi kartu, prieš demonstraciją)
Po to, kai visos 4 šakos sulietos į `main`:
- Patikrinti, kad `app/__init__.py` registruoja visus blueprint'us (`ak_bp`, `tvk_bp`,
  `tvk_week_bp`, `dvk_bp`).
- Papildyti `app/gvs/templates/base.html` navigacijos nuorodomis į visus 4 langus.
- Patikrinti `db/seed.sql`, kad kiekvienoje lentelėje būtų 3-5 realūs įrašai (N-16).
- Pereiti pagrindinį scenarijų nuo registracijos iki konflikto pastebėjimo (žr. 20 pav.
  sekų diagramą dokumente).
