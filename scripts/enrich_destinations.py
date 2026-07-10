"""Arricchimento one-off delle destinazioni: gallery foto + scheda Wikipedia.

Per ogni waypoint votato in voyage.json raccoglie da Wikimedia:
  - una GALLERY di foto (Commons, geosearch per coordinate)
  - la scheda Wikipedia piu' pertinente (intro storico/descrittivo + link)
e scrive data/destinations.json (COMMITTATO, rivedibile con git diff).

  python scripts/enrich_destinations.py            # completa le voci mancanti
  python scripts/enrich_destinations.py --only girolata
  python scripts/enrich_destinations.py --refresh  # riforza tutto
  python scripts/enrich_destinations.py --limit 5  # solo le prime 5 mancanti

Perche' one-off e committato: Wikipedia/Commons rate-limitano le raffiche
(429) e su carta la CI non deve MAI chiamarli. publish.py legge solo questo
file. Riusa cache/throttle/circuit-breaker di photos._get: se scatta il 429
lo script si ferma e salva quel che ha; si completa piu' tardi con --refresh.

L'articolo non e' scelto per pura vicinanza (il piu' vicino a Bonifacio e' una
chiesa): si preferisce il match del NOME nel titolo; se nessuna lingua da' un
match, wiki resta null (meglio niente che l'articolo sbagliato).
"""
from __future__ import annotations
import argparse, datetime as dt, json, urllib.parse
from pathlib import Path

import core, photos

DEST_FILE = core.DATA / "destinations.json"
WIKI_LANGS = ("it", "fr", "en")   # Corsica spesso solo fr, La Maddalena it
EXTRACT_MAX = 1500
# titoli "struttura": la chiesa/stazione/faro taggata sul posto NON deve
# battere l'articolo del luogo (Bonifacio-paese vs "Chiesa ... (Bonifacio)")
STRUCT_WORDS = ("chiesa", "eglise", "église", "stazione", "gare", "phare", "faro",
                "museo", "musée", "cattedrale", "cathédrale", "chapelle", "cappella",
                "fort", "tour ", "torre", "aeroporto", "aéroport", "aeroport",
                "battaglia", "bataille", "monument",
                # divisioni amministrative/derivate: il paese batte il "cantone di…"
                "cantone", "canton", "arrondissement", "comunità", "communauté")


def _wiki_get(lang: str, params: dict) -> dict:
    p = {"format": "json", **params}
    return photos._get(f"https://{lang}.wikipedia.org/w/api.php", p)


def _clip(text: str, limit: int = EXTRACT_MAX) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > limit * 0.5 else cut.rstrip()) + " […]"


def wiki_article(lat: float, lon: float, name: str) -> dict | None:
    """Scheda Wikipedia piu' pertinente: {lang, title, extract, url} o None.
    Prova it -> fr -> en; sceglie per match del nome, non per vicinanza."""
    tokens = photos.tokens_of(name)
    if not tokens:
        return None
    for lang in WIKI_LANGS:
        try:
            geo = _wiki_get(lang, {"action": "query", "list": "geosearch",
                                   "gscoord": f"{lat}|{lon}", "gsradius": 3000,
                                   "gslimit": 10})
        except Exception:
            if photos._rate_limited[0]:
                return None
            continue
        hits = ((geo.get("query") or {}).get("geosearch")) or []
        # solo gli articoli il cui titolo contiene una parola-chiave del nome
        matched = [h for h in hits
                   if any(t in h["title"].lower() for t in tokens)]
        if not matched:
            continue

        def rank(h):
            title = h["title"].lower()
            no_struct = not any(s in title for s in STRUCT_WORDS)
            nmatch = sum(1 for t in tokens if t in title)
            # a parita', il titolo piu' corto e' di solito il luogo stesso
            # ("Bonifacio" batte "Cantone di Bonifacio")
            nwords = len(title.replace("(", " ").replace(")", " ").split())
            return (no_struct, nmatch, -nwords, -h.get("dist", 9e9))
        best = max(matched, key=rank)
        try:
            ex = _wiki_get(lang, {"action": "query", "prop": "extracts|info",
                                  "exintro": 1, "explaintext": 1, "inprop": "url",
                                  "redirects": 1, "titles": best["title"]})
        except Exception:
            return None
        pages = (ex.get("query") or {}).get("pages") or {}
        page = next(iter(pages.values()), {})
        extract = _clip(page.get("extract", ""))
        if not extract:
            continue
        url = page.get("fullurl") or (
            f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(best["title"].replace(" ", "_")))
        return {"lang": lang, "title": best["title"], "extract": extract, "url": url}
    return None


def load_dest() -> dict:
    try:
        return json.loads(DEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": {}}


def main() -> None:
    ap = argparse.ArgumentParser(description="Arricchisce le destinazioni (foto + Wikipedia)")
    ap.add_argument("--only", metavar="ID", help="una sola destinazione")
    ap.add_argument("--refresh", action="store_true", help="riforza anche le voci gia' presenti")
    ap.add_argument("--limit", type=int, help="al massimo N destinazioni (test)")
    a = ap.parse_args()

    v = core.load()
    rated = [w for w in v["waypoints"] if w.get("rating") is not None]
    doc = load_dest()
    entries = doc.setdefault("entries", {})

    todo = [w for w in rated if (
        w["id"] == a.only if a.only else (a.refresh or w["id"] not in entries))]
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        print("Niente da fare (tutte le voci presenti; usa --refresh per riforzare).")
        return

    print(f"Arricchisco {len(todo)} destinazioni su {len(rated)} votate…")
    done = 0
    for w in todo:
        if photos._rate_limited[0]:
            print("  Wikimedia rate-limited: mi fermo, rilancia con --refresh piu' tardi.")
            break
        gal = photos.gallery_for(w["lat"], w["lon"], w["name"], n=6, width=800)
        wiki = wiki_article(w["lat"], w["lon"], w["name"])
        if photos._rate_limited[0]:
            # il 429 e' scattato DURANTE questa voce: gallery/wiki sono parziali
            # (un wiki:null qui non e' "nessun articolo", e' "non ho potuto
            # chiedere"). Scarto e mi fermo: si rilancia e la cache fa il resto.
            print(f"  {w['id']}: rate-limited a meta', scarto la voce parziale.")
            break
        entries[w["id"]] = {"coords": [w["lat"], w["lon"]], "gallery": gal, "wiki": wiki}
        done += 1
        tag = f"wiki:{wiki['lang']}/{wiki['title'][:28]}" if wiki else "wiki:—"
        print(f"  {w['id']:<22} {len(gal)} foto  {tag}")

    doc["generated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    tmp = DEST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DEST_FILE)

    tot = len(entries)
    with_wiki = sum(1 for e in entries.values() if e.get("wiki"))
    no_photo = [k for k, e in entries.items() if not e.get("gallery")]
    print(f"\nScritto {DEST_FILE.name}: {tot} voci ({done} nuove/aggiornate), "
          f"{with_wiki} con Wikipedia.")
    if no_photo:
        print(f"Senza foto: {no_photo}")
    print("Rivedi con `git diff data/destinations.json` prima di committare.")


if __name__ == "__main__":
    main()
