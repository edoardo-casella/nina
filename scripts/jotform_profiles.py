# -*- coding: utf-8 -*-
"""Pipeline questionario equipaggio (Jotform) -> staging locale per i profili del sito.

Il form "Questionario Equipaggio - Nina" (261907242193053) raccoglie le risposte
dei membri 2026. Questo script fa la parte DETERMINISTICA della pipeline:

  --check            elenca le submission nuove (non ancora in data/jotform-processed.json)
  --fetch            per ogni nuova: scrive lo staging in data/jotform-inbox/<cid>-<sub>.json
                     (GITIGNORED: contiene email e dati sanitari) + scarica la foto in
                     data/Profili/<cid>.<ext> (gitignored) e marca la submission processata
  --refetch <subid>  ri-scarica staging+foto di una submission gia' processata
  --delete <subid>   cancella una submission da Jotform (es. le risposte di prova)

La parte GENERATIVA (bio, epiteto, tag nel tono del sito) resta all'agente, che legge
lo staging e scrive data/crew-bios.json / data/crew-tags.json / NICKS di build_crew.py.
REGOLE PRIVACY (promesse nel form): il blocco `riservati_non_pubblicare` dello staging
(email, allergie, cambusa, adesioni economiche) NON va mai pubblicato sul sito.

Richiede una API key Jotform FULL ACCESS nell'env var JOTFORM_API_KEY (mai nei file:
serve anche a scaricare gli upload protetti da login appendendo ?apiKey=... all'URL).
"""
import io, json, os, re, sys, unicodedata, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORM_ID = "261907242193053"
API = "https://api.jotform.com"
PROCESSED = os.path.join(ROOT, "data", "jotform-processed.json")
INBOX = os.path.join(ROOT, "data", "jotform-inbox")
PROFILI = os.path.join(ROOT, "data", "Profili")
CREWJSON = os.path.join(ROOT, "site", "data", "crew.json")

KEY = os.environ.get("JOTFORM_API_KEY", "").strip()
if not KEY:
    sys.exit("JOTFORM_API_KEY mancante nell'ambiente (serve una key Jotform full-access).")

# Campi del form per `name` (stabili anche se cambia l'ordine delle domande).
# Pubblicabili = materiale per bio/tag/nick; riservati = MAI sul sito (promessa nel form).
PUBBLICABILI = {
    "nomeE": "nome_e_cognome",          # serve solo a risolvere il crew_id, non si pubblica intero
    "ilTuo": "nickname",
    "quanteVolte": "volte_in_barca", "haiLa": "patente", "haiFrequentato": "scuola_vela",
    "quanteVacanze": "vacanze_da_passeggero", "quanteVacanze13": "vacanze_da_skipper",
    "comeTi": "come_si_definisce", "perQuali": "ruoli_candidati",
    "quantoTi": "quanto_vela_1_5", "tiPiacerebbe": "vuole_imparare", "seiPiu": "nottambulo_1_5",
    "tiVa": "minicorso_nodi", "iTuoi": "pregi", "iTuoi20": "difetti",
    "leCose": "ama_in_barca", "leCose48": "odia_in_barca",
    "raccontaciUn": "aneddoto_anni_scorsi", "laTua45": "esperienza_epica", "ilTuo46": "errore_fatale",
    "seiGia": "gia_col_comandante", "aneddotiDelle": "aneddoti_col_comandante",
    "iPregi": "pregi_comandante", "iDifetti": "difetti_comandante",
    "seTi": "esperienza_cucina", "input24": "ricetta_proposta", "unCibopiatto": "cibo_immancabile",
    "piattiChe": "piatti_che_ama", "qualcosaChe": "note_libere",
}
RISERVATI = {
    "laTua": "email", "haiAllergie": "allergie_intolleranze",
    "cheAcqua": "acqua", "qualiBibite": "bibite", "specialitaSarde": "specialita_sarde",
    "cheTipo": "spiagge", "cheProfondita": "profondita", "Sup": "giochi_acqua",
    "assicurazioneCasco": "assicurazione_casco", "supA": "sup_quota",
}
CID_ALIAS = {"edoardo-c": "edo-c", "gabriele-m": "gabri-m", "federico-b": "fede-b"}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()).strip("-")


def crew_id_of(fullname):
    """'Giulia Nesi' -> 'giulia-n', come build_crew.py (nome + iniziale cognome)."""
    parts = fullname.strip().split()
    if len(parts) < 2:
        return slugify(fullname)
    cid = slugify(parts[0] + " " + parts[-1][:1])
    return CID_ALIAS.get(cid, cid)


def known_ids():
    try:
        crew = json.loads(io.open(CREWJSON, encoding="utf-8").read())["people"]
        return {x["id"] for x in crew}
    except OSError:
        return set()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nina-jotform-profiles"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get_content_type(), r.read()


def api(path, method="GET"):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(f"{API}/{path}{sep}apiKey={KEY}", method=method,
                                 headers={"User-Agent": "nina-jotform-profiles"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_processed():
    if os.path.exists(PROCESSED):
        return json.loads(io.open(PROCESSED, encoding="utf-8").read())
    return {"form_id": FORM_ID, "processed": []}


def submissions():
    out = api(f"form/{FORM_ID}/submissions?limit=1000")
    return [s for s in out.get("content", []) if s.get("status") == "ACTIVE"]


def parse(sub):
    """Splitta le risposte nei due blocchi pubblicabili/riservati."""
    pub, ris, photo_urls = {}, {}, []
    for a in sub.get("answers", {}).values():
        name, ans = a.get("name"), a.get("answer")
        if ans in (None, "", []):
            continue
        if name == "unaTua":
            photo_urls = ans if isinstance(ans, list) else [ans]
        elif name in PUBBLICABILI:
            pub[PUBBLICABILI[name]] = ans
        elif name in RISERVATI:
            ris[RISERVATI[name]] = ans
    return pub, ris, photo_urls


def fetch_one(sub, ids):
    sid = sub["id"]
    pub, ris, photos = parse(sub)
    nome = pub.get("nome_e_cognome", "")
    cid = crew_id_of(nome)
    if cid not in ids:
        print(f"  ATTENZIONE: '{nome}' -> {cid} non trovato in crew.json (nuovo membro? id da verificare)")
    os.makedirs(INBOX, exist_ok=True)
    staging = os.path.join(INBOX, f"{cid}-{sid}.json")
    io.open(staging, "w", encoding="utf-8").write(json.dumps(
        {"submission_id": sid, "created_at": sub.get("created_at"), "crew_id": cid,
         "pubblicabili": pub, "riservati_non_pubblicare": ris},
        ensure_ascii=False, indent=2))
    print(f"  staging: {os.path.relpath(staging, ROOT)}")
    for url in photos:
        ext = os.path.splitext(url)[1].lower() or ".jpg"
        dest = os.path.join(PROFILI, cid + ext)
        if os.path.exists(dest):
            print(f"  foto: {os.path.relpath(dest, ROOT)} esiste gia', salto")
            continue
        try:
            ctype, blob = get(url + ("&" if "?" in url else "?") + "apiKey=" + KEY)
        except (urllib.error.URLError, OSError) as e:
            print(f"  foto: download fallito ({e}) -> scaricala a mano dall'inbox Jotform")
            continue
        # il login wall risponde text/html; il file vero arriva come image/* o octet-stream:
        # fidati dei magic bytes, non del content-type
        magic_ok = blob[:2] == b"\xff\xd8" or blob[:8] == b"\x89PNG\r\n\x1a\n" or blob[:4] == b"RIFF" or blob[4:12] == b"ftypheic"
        if not magic_ok:
            print(f"  foto: risposta {ctype}, non sembra un'immagine (login wall?) -> scaricala a mano dall'inbox Jotform")
            continue
        os.makedirs(PROFILI, exist_ok=True)
        io.open(dest, "wb").write(blob)
        print(f"  foto: {os.path.relpath(dest, ROOT)} ({len(blob)//1024} KB) -> poi add_profile_photos.py")


def main():
    args = sys.argv[1:]
    state = load_processed()
    done = set(state["processed"])
    if "--delete" in args:
        sid = args[args.index("--delete") + 1]
        out = api(f"submission/{sid}", method="DELETE")
        print(f"submission {sid}: {out.get('message', out)}")
        return
    subs = submissions()
    if "--refetch" in args:
        sid = args[args.index("--refetch") + 1]
        target = [s for s in subs if s["id"] == sid]
        if not target:
            sys.exit(f"submission {sid} non trovata")
        fetch_one(target[0], known_ids())
        return
    nuove = [s for s in subs if s["id"] not in done]
    print(f"{len(subs)} submission attive, {len(nuove)} nuove")
    for s in nuove:
        nome = next((a.get("answer") for a in s.get("answers", {}).values() if a.get("name") == "nomeE"), "?")
        print(f"- {s['id']} · {s.get('created_at')} · {nome}")
    if "--fetch" in args and nuove:
        ids = known_ids()
        for s in nuove:
            fetch_one(s, ids)
            state["processed"].append(s["id"])
        io.open(PROCESSED, "w", encoding="utf-8").write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        print(f"processed aggiornato: {len(state['processed'])} totali")


if __name__ == "__main__":
    main()
