# Genera site/data/trips.json + ottimizza le foto viaggio in site/trips/img/<id>/.
import openpyxl, collections, os, glob, re, unicodedata, json
from PIL import Image, ImageOps

ROOT = r"c:\Users\Edo\OneDrive - Bologna Business School\1.Progettazione\99_AI_Workspace\35_SailingAgent"
CV = os.path.join(ROOT, "data", "Skipper CV Enriched.xlsx")
import shutil, tempfile
_cvtmp = os.path.join(tempfile.gettempdir(), "nina_cv_read.xlsx")
shutil.copy(CV, _cvtmp)  # copia: il file OneDrive/Excel puo' essere lockato
CREWDIR = os.path.join(ROOT, "data", "Skipper Images", "Crew")
OUTIMG = os.path.join(ROOT, "site", "trips", "img")

wb = openpyxl.load_workbook(_cvtmp, data_only=True)
people = {}
for r in wb["Passengers"].iter_rows(min_row=2, values_only=True):
    if r[0] is None: continue
    people[int(r[0])] = {"cog": (r[1] or "").strip(), "nom": (r[2] or "").strip()}
def ini(p):
    pp = people.get(p, {})
    return (pp.get("nom", "") + " " + (pp.get("cog", "")[:1] + "." if pp.get("cog") else "")).strip() or ("#" + str(p))

trips = {}
for r in wb["Summary"].iter_rows(min_row=2, values_only=True):
    if r[0] in (None, "TOTAL"): continue
    try: tid = int(float(r[0]))
    except: continue
    trips[tid] = {"year": int(float(r[1])), "month": r[2], "country": (r[4] or "").strip(),
                  "zone": (r[5] or "").strip(), "boat": (r[6] or "").strip(),
                  "name": (r[8] or "").strip(), "nm": int(float(r[9])), "days": float(r[10])}
crew = collections.defaultdict(list)
for r in wb["Participations"].iter_rows(min_row=2, values_only=True):
    if r[0] is None or r[2] is None: continue
    try: t = int(r[0]); p = int(r[2])
    except: continue
    crew[t].append(p)

KW = {"grecia": "Greece", "croazia": "Croazia", "spagna": "Spain", "sardegna": "Italy", "sicilia": "Italy"}
def norm(s): return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if c.isalnum() or c == " ")
photos = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(CREWDIR, "*"))):
    b = os.path.basename(f); nl = norm(b); yr = re.search(r"(20[0-2][0-9])", b)
    kw = next((k for k in KW if k in nl), None)
    if any(x in nl for x in ("moneglia", "incident", "trouble")) or not yr or not kw: continue
    y = int(yr.group(1)); country = KW[kw]
    cands = [t for t, m in trips.items() if m["year"] == y and country in str(m["country"])]
    if country == "Italy":
        zk = "sardegna" if "sardegna" in nl else ("sicil" if "sicilia" in nl else None)
        cands = [t for t in cands if zk and zk in norm(str(trips[t]["zone"]))]
    if len(cands) == 1: photos[cands[0]].append(f)

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()).strip("-")

out = []
for t in sorted(trips):
    m = trips[t]; tid = slug(m["name"]) or ("t" + str(t))
    phs = []
    if photos.get(t):
        d = os.path.join(OUTIMG, tid); os.makedirs(d, exist_ok=True)
        for i, src in enumerate(sorted(photos[t]), 1):
            im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
            mx = 1280
            if max(im.size) > mx:
                sc = mx / max(im.size); im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
            fn = "%02d.jpg" % i
            im.save(os.path.join(d, fn), "JPEG", quality=82, optimize=True, progressive=True)
            phs.append({"src": "trips/img/%s/%s" % (tid, fn), "w": im.width, "h": im.height})
    out.append({"id": tid, "year": m["year"], "month": m["month"], "country": m["country"],
                "zone": m["zone"], "boat": m["boat"], "name": m["name"], "nm": m["nm"],
                "days": round(m["days"], 1), "crew": [ini(p) for p in crew.get(t, [])],
                "n_photos": len(phs), "photos": phs})

data = {"generated_at": "2026-07-11", "trips": out}
with open(os.path.join(ROOT, "site", "data", "trips.json"), "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
tot = sum(t["n_photos"] for t in out)
print("trips.json:", len(out), "viaggi,", tot, "foto ottimizzate")
for t in out:
    if t["n_photos"]: print("  ", t["id"], t["year"], t["country"], "->", t["n_photos"], "foto,", len(t["crew"]), "crew")
