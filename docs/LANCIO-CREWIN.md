# Lancio Crewin — runbook (dominio: everywaves.com)

> **FASE B 2026-07-16: il dominio scelto è EVERYWAVES.COM** (comprato su GoDaddy; crewin.it
> abbandonato — mai registrato). DNS: 4 A → GitHub Pages + CNAME www → @ su GoDaddy.
> Custom domain impostato via API, `site/CNAME` nel repo, auth Supabase su everywaves.com.
> Le sezioni sotto che citano "crewin.it" valgono lette come "everywaves.com".

> **STATO 2026-07-15 — FASE A COMPLETATA (live senza dominio).** Area riservata attiva su
> `https://edoardo-casella.github.io/nina/` — Supabase progetto **Plancia** (`nlbhhzjimsxakcugmrdy`,
> Frankfurt): schema+RLS applicati, auth configurata (magic link → auth-callback), seed fatto
> (edo-c admin + 2 email Jotform, 17 profili), secret CI attivi (upsert conti = keep-alive),
> RLS verificata. Email: mailer integrato Supabase (~2-4/h) finché non c'è Resend.
> **Aggiornamento 2026-07-16 (decisioni Edo): schede personali PUBBLICHE (RLS select ad anon su
> profiles) e arrivi/partenze + date d'imbarco di nuovo PUBBLICI (site/data/arrivi.json statico,
> date in crew.json/briefing). Riservati: SOLO conti, editor profilo, admin.**
> **Restano: la Fase B qui sotto (dominio) + nota due-progetti in fondo.**

Porta il sito da `edoardo-casella.github.io/nina` a **crewin.it** con area riservata
(login magic-link, Supabase free). Il codice è già pronto sul branch: questo file è la
sequenza dei passi — quelli marcati **[EDO]** sono manuali, il resto è verificabile da Claude Code.

Architettura: GitHub Pages invariato per tutto il pubblico; Supabase (Auth + Postgres RLS)
per i soli dati riservati: `conti`, `arrivi` (blob scritti dalla CI), `profiles` (schede
editabili), `members`/`access_requests` (accessi con approvazione). Schema: `supabase/schema.sql`.

## 0 · Prerequisiti [EDO]

1. **Compra crewin.it** — consigliato Aruba (~4 € il 1° anno, ~14,6 €/anno al rinnovo) oppure OVH.
   Serve solo il dominio con pannello DNS: niente hosting del registrar.
   (Cloudflare Registrar non supporta i .it.)
2. **Account Supabase** (free): crea il progetto `crewin`, region EU (Francoforte).
3. **Account Resend** (free, 100 email/giorno): servirà come SMTP per i magic link —
   il mailer integrato di Supabase è rate-limitato (~2-4/h), non basta per l'onboarding.

## 1 · DNS [EDO]

Nel pannello DNS del registrar:

| Tipo | Nome | Valore |
|---|---|---|
| A | @ | 185.199.108.153 |
| A | @ | 185.199.109.153 |
| A | @ | 185.199.110.153 |
| A | @ | 185.199.111.153 |
| CNAME | www | edoardo-casella.github.io |
| TXT/CNAME | (quelli richiesti da Resend per SPF/DKIM al passo 3) | |

## 2 · Supabase

1. [EDO] SQL Editor → incolla ed esegui `supabase/schema.sql` (idempotente).
2. [EDO] Authentication → Providers: solo **Email**, disattiva "Email+Password" signup se offerto,
   resta il magic link (OTP). Authentication → URL Configuration:
   - Site URL: `https://crewin.it`
   - Redirect URLs: `https://crewin.it/auth-callback.html` (+ `https://edoardo-casella.github.io/nina/auth-callback.html` come transizione)
3. [EDO] Project Settings → API: copia **URL**, **anon key**, **service_role key**.
4. Config locale/CI:
   - `site/config.js`: riempi `SUPABASE_URL` e `SUPABASE_ANON_KEY` (la anon è pubblica per costruzione).
   - [EDO] GitHub → repo nina → Settings → Secrets and variables → Actions:
     `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` (service_role — MAI nel codice).
   - In locale (per seed e publish manuali): env-var utente `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`.

## 3 · Email (Resend) [EDO]

1. Resend → Domains → aggiungi `crewin.it`, metti i record DNS richiesti (SPF/DKIM), attendi verifica.
2. Resend → API Keys → crea una chiave SMTP.
3. Supabase → Authentication → Emails → SMTP settings: host `smtp.resend.com`, porta 465,
   user `resend`, password = API key, mittente `ciurma@crewin.it` (o simile).
4. Facoltativo: personalizza il template "Magic Link" in italiano.

## 4 · Seed dei dati (ORDINE IMPORTANTE)

Il seed copia le schede `q` dal `crew.json` corrente: va fatto **PRIMA** di rigenerare
`crew.json` (il nuovo `build_crew.py` non le emette più).

```bash
python scripts/seed_supabase.py --dry-run   # controlla members/profiles proposti
python scripts/seed_supabase.py             # esegue (env-var pronte)
python scripts/build_crew.py                # rigenera crew.json SENZA q/board/leave
python scripts/publish.py                   # rigenera i JSON + primo upsert conti/arrivi
```

Verifica: in Supabase Table Editor `members` ha lo skipper admin + le email Jotform;
`profiles` ha i membri 2026 (2 con scheda piena); `private_blobs` ha `conti` e `arrivi`.

## 5 · Go-live

1. Crea `site/CNAME` con dentro solo `crewin.it` — **solo ora**: prima del DNS
   romperebbe il sito live.
2. Commit + push del branch (`git push origin claude/nina:main`) → Actions builda e deploya.
3. [EDO] GitHub → Settings → Pages → Custom domain: `crewin.it` → attendi verifica →
   spunta **Enforce HTTPS** (il certificato può metterci da minuti a qualche ora).
4. Verifiche:
   - `https://crewin.it` risponde in HTTPS, pagine pubbliche identiche a prima;
   - `https://edoardo-casella.github.io/nina/` **redirige** a crewin.it;
   - `https://crewin.it/data/conti.json` → 404;
   - login end-to-end: richiesta da unisciti → approvazione in admin.html → magic link
     → conti visibili in plancia, arrivi visibili, scheda in membro.html → edit da profilo.html;
   - con utente NON approvato: zero dati (`curl` su `/rest/v1/private_blobs` con anon key → `[]`);
   - PWA: reinstallala da crewin.it (le vecchie installazioni github.io seguono il redirect ma
     conviene reinstallare — avvisare la ciurma).

## 6 · Post-lancio

- Annuncio alla ciurma: nuovo indirizzo + come chiedere l'accesso + reinstallare la PWA.
- Aggiornare gli URL in `CLAUDE.md` e `OPERATIONS.md` (github.io → crewin.it) e la memoria workspace.
- `og:url` sulle pagine principali (facoltativo).
- Backup: ogni tanto `pg_dump` dal pannello Supabase o export CSV delle 4 tabelle.

## Costi annuali

| Voce | Anno 1 | Regime |
|---|---|---|
| Dominio crewin.it | ~5 € | ~15 € |
| GitHub Pages + Actions | 0 € | 0 € |
| Supabase Free (keep-alive: la CI scrive 2x/die) | 0 € | 0 € |
| Resend Free (100 email/giorno) | 0 € | 0 € |
| **Totale** | **~5 €** | **~15 €** |

Upgrade solo se servono: Supabase Pro (25 $/mese) per backup automatici; GitHub Pro per repo privato.

## Nota: DUE progetti Supabase (2026-07-15)

Il sito usa due progetti su due account Supabase distinti:
1. **Plancia** (`nlbhhzjimsxakcugmrdy`, account GitHub-login) — area riservata. Keep-alive: CI 2x/die.
2. **nina-crewin** (`omxohvtjeanbdbxrdenx`, account preesistente con GestioneCondomini, connettore
   claude.ai) — **like degli aneddoti** (tabella `nina_likes`, anon key hardcoded in aneddoti.html).
   ⚠️ NESSUN keep-alive: senza traffico per 7 giorni il free tier lo PAUSA e i like spariscono
   in silenzio (contatori a zero/offline). Opzioni: (a) consolidare i like dentro Plancia
   (tabella+vista+RLS migrate, ripuntare LIKES_API, poi dismettere nina-crewin) — consigliato;
   (b) aggiungere in update.yml un ping alla REST di nina-crewin. NON dismettere nina-crewin
   prima di aver migrato i like.

## Note di sicurezza

- La **anon key** in `config.js` è pubblica per design: senza sessione approvata le policy RLS
  restituiscono zero righe (`supabase/schema.sql`).
- La **service_role key** vive SOLO nei GitHub Actions secrets e nelle env-var locali.
- I dati riservati non sono mai nell'artifact statico: `conti.json` rimosso (i conti vivono solo
  nel blob Supabase dietro RLS). Schede, arrivi e date d'imbarco sono pubblici per scelta.
- Storia git: le vecchie revisioni di `conti.json` (dati placeholder) e le 2 schede `q`
  (contenuto già autorizzato, iniziali) restano nella history — scelta consapevole, niente force-push.
