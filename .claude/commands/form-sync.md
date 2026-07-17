---
description: Sync automatico questionario equipaggio → sito (headless, ogni 4h)
---

Sei nel worktree `C:\nina-work\claude` (branch `claude/nina` del sito Everywaves).
Routine NON presidiata: niente domande, log chiaro, esci appena non c'è lavoro.

## Passo 1 — check (sempre, poi esci se vuoto)
Esegui `python scripts/jotform_profiles.py --check` (JOTFORM_API_KEY è in env).
Se le nuove submission sono 0: stampa "form-sync: niente di nuovo" e FERMATI qui.

## Passo 2 — pipeline per ogni submission nuova (contratto autorizzato)
1. `python scripts/jotform_profiles.py --fetch` (staging privato + eventuale foto).
2. **Foto**: se presente, guardala (Read del file in `data/Profili/`). Se è un
   ritratto usabile → `python scripts/add_profile_photos.py`. Se NON è un ritratto
   (cibo, screenshot, buio) → salta la foto e annotalo nel log; il resto procede.
   Se arriva ruotata non preoccuparti: lo script raddrizza via EXIF.
3. **Supabase** (env `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`, upsert via REST):
   - `profiles`: compila SOLO i campi NULL (regola: l'editor del membro vince)
     con nick/ruolo/esperienza/specialita/valigia/motto/funfact derivati dalle
     risposte `pubblicabili`, nel tono del sito (vedi schede esistenti). MAI
     dieta/allergie. MAI campi calcolati.
   - `members`: insert `crew_id + email` (da `riservati_non_pubblicare`) status
     `approved`, `on conflict do nothing`. L'email non finisce MAI nel repo o nel sito.
4. **Registro**: nickname nuovo → aggiungilo a `NICKS` in `scripts/build_crew.py`
   (in coda alla lista esistente della persona, o voce nuova); 1-2 tag da
   questionario in `data/crew-tags.json` (stile compatto esistente). NON toccare
   bio editoriali esistenti.
5. **Rebuild**: `python scripts/build_crew.py` poi `python scripts/publish.py`
   (con env Supabase). Verifica che crew.json non contenga mai `q`, email o allergie.
6. **Commit & push**:
   - `git fetch origin && git merge --ff-only origin/main` (se diverge: rebase; il file
     `data/jotform-processed.json` va salvaguardato con copia temporanea prima di
     qualsiasi checkout, poi ripristinato — è sulla junction dei dati canonici).
   - Stage: `git add --sparse data/crew-tags.json data/jotform-processed.json` +
     i file `site/` toccati + `scripts/build_crew.py` se cambiato.
   - ⚠️ Per OGNI file `data/…` staged verifica il blob: `git show :data/<file>`
     deve contenere la modifica (lo sparse-checkout può tenerti il contenuto
     vecchio in silenzio; se succede: `git update-index --no-skip-worktree <file>`,
     re-add, e a fine commit ripristina `--skip-worktree`).
   - Commit con messaggio "Questionario: profilo di <Nome> (form-sync automatico)"
     + trailer `Co-Authored-By: Claude <noreply@anthropic.com>`, poi
     `git push origin claude/nina:main`. MAI force-push, MAI history rewrite.

## Fuori scope (sempre)
- Google Form (aneddoti / profilo di bordo / candidature): il connettore Drive
  non esiste in headless — li gestisce la sessione interattiva.
- Qualsiasi cosa ambigua (crew_id sconosciuto, omonimie, contenuti che espongono
  terzi): NON pubblicare quella parte, annota nel log e prosegui col resto.

## Output finale
Una riga per submission processata: nome, cosa è stato aggiornato (foto/scheda/
tag/nick), e l'hash del commit. Oppure "form-sync: niente di nuovo".
