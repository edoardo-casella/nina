# -*- coding: utf-8 -*-
# Dataset unico crew.json: 2026 crew (nickname) + alumni (registro), con giorni,
# viaggi, anni e grado navale (per seniority = giorni in barca).
import openpyxl, collections, json, re, unicodedata, io, os
ROOT = r"c:\Users\Edo\OneDrive - Bologna Business School\1.Progettazione\99_AI_Workspace\35_SailingAgent"
CV = os.path.join(ROOT, "data", "Skipper CV Enriched.xlsx")
import shutil, tempfile
_cvtmp = os.path.join(tempfile.gettempdir(), "nina_cv_read.xlsx")
try:
    shutil.copy(CV, _cvtmp)  # copia: il file OneDrive/Excel puo' essere lockato
except PermissionError:
    if not os.path.exists(_cvtmp): raise   # nessuna copia utilizzabile -> chiudi Excel
    print("CV lockato da Excel/OneDrive: uso la copia temp esistente", _cvtmp)
CREWJSON = os.path.join(ROOT, "site", "data", "crew.json")
# la zona "Inner Islands" (crociera Seychelles) va mostrata come "Seychelles"
ZONE_OVERRIDE = {"Inner Islands": "Seychelles"}

wb = openpyxl.load_workbook(_cvtmp, data_only=True)
people = {}
for r in wb["Passengers"].iter_rows(min_row=2, values_only=True):
    if r[0] is None: continue
    people[int(r[0])] = {"cog": (r[1] or "").strip(), "nom": (r[2] or "").strip()}
trip_days, trip_year, trip_nm = {}, {}, {}
trip_name, trip_zone, trip_country, trip_boat = {}, {}, {}, {}
for r in wb["Summary"].iter_rows(min_row=2, values_only=True):
    if r[0] in (None, "TOTAL"): continue
    try: t = int(float(r[0]))
    except: continue
    trip_year[t] = int(float(r[1])); trip_days[t] = float(r[10]); trip_nm[t] = int(float(r[9]))
    trip_name[t] = (r[8] or "").strip(); _z = (r[5] or "").strip(); trip_zone[t] = ZONE_OVERRIDE.get(_z, _z)
    trip_country[t] = (r[4] or "").strip(); trip_boat[t] = (r[6] or "").strip()
part = collections.defaultdict(list)       # pid -> [trip id]
roster = collections.defaultdict(list)     # trip id -> [pid]  (per la co-navigazione)
part_days, part_nm = {}, {}                 # (trip, pid) -> giorni/miglia PER-PERSONA
for r in wb["Participations"].iter_rows(min_row=2, values_only=True):
    if r[0] is None or r[2] is None: continue
    try: t = int(r[0]); p = int(r[2])
    except: continue
    part[p].append(t); roster[t].append(p)
    try: part_days[(t, p)] = float(r[6]) if r[6] is not None else None
    except: part_days[(t, p)] = None
    try: part_nm[(t, p)] = float(r[7]) if r[7] is not None else None
    except: part_nm[(t, p)] = None

def norm(s): return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if c.isalnum())
def slugify(s): return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()).strip("-")
def pname(p):
    pp = people[p]; return (pp["nom"] + " " + (pp["cog"][:1] + "." if pp["cog"] else "")).strip() or pp["cog"] or ("#" + str(p))

def pdays(t, p): return part_days.get((t, p)) if part_days.get((t, p)) is not None else trip_days.get(t, 0)
def pnm(t, p):   return part_nm.get((t, p))   if part_nm.get((t, p))   is not None else trip_nm.get(t, 0)

def stats(p):  # giorni/miglia PER-PERSONA (alcuni sono a bordo meno del totale viaggio)
    ts = part.get(p, [])
    days = round(sum(pdays(t, p) for t in ts))
    nm = round(sum(pnm(t, p) for t in ts))
    ys = [trip_year.get(t) for t in ts if trip_year.get(t)]
    return {"trips": len(ts), "days": days, "nm": nm, "first": min(ys) if ys else None, "last": max(ys) if ys else None}

def trips_list_for(ts, pid=None):  # log viaggi cliccabile: id-slug (parita' con build_trips), + boat/nm/days (per pace/icona) + pdays (giorni a bordo di QUESTA persona; None -> intero viaggio)
    rows = []
    for t in sorted(ts, key=lambda t: (trip_year.get(t, 0), t)):
        rows.append({"id": slugify(trip_name.get(t, "")) or ("t" + str(t)),
                     "year": trip_year.get(t), "zone": trip_zone.get(t, ""), "country": trip_country.get(t, ""),
                     "boat": trip_boat.get(t, ""), "nm": trip_nm.get(t, 0), "days": round(trip_days.get(t, 0)),
                     "pdays": round(pdays(t, pid)) if pid is not None else round(trip_days.get(t, 0))})
    return rows

def companions_for(p):  # con chi ha navigato di piu' (peso: n. viaggi condivisi, tie-break giorni)
    if p is None: return []
    cnt, dsum = collections.Counter(), collections.Counter()
    for t in part.get(p, []):
        for q in roster.get(t, []):
            if q == p: continue
            cnt[q] += 1
            dsum[q] += round(min(pdays(t, p), pdays(t, q)))
    ranked = sorted(cnt, key=lambda q: (cnt[q], dsum[q]), reverse=True)  # TUTTI i co-naviganti (filtro id dopo l'ordinamento, non prima: altrimenti gli stub tagliavano il conteggio)
    res = []
    for q in ranked:
        qid = pid2id.get(q)
        if qid: res.append({"id": qid, "name": id2name.get(qid, ""), "trips": cnt[q], "days": dsum[q]})
    return res

def match(name):  # voyage nickname -> registry pid
    parts = name.strip().split()
    if len(parts) < 2: return None
    first = norm(parts[0]); si = norm(parts[-1])[:1]
    cands = [pid for pid, pp in people.items() if norm(pp["nom"]).startswith(first[:4]) and norm(pp["cog"])[:1] == si]
    return max(cands, key=lambda p: len(part.get(p, []))) if cands else None

# gradi navali per giorni in barca
RANKS = [  # (min_days, id, label)
    (250, "admiral", "Ammiraglio"),
    (140, "capt", "Capitano di vascello"),
    (95,  "cdr", "Capitano di fregata"),
    (60,  "ltcdr", "Capitano di corvetta"),
    (35,  "lt", "Tenente di vascello"),
    (18,  "ltjg", "Sottotenente di vascello"),
    (7,   "ensign", "Guardiamarina"),
    (0,   "recruit", "Allievo"),
]
def rank_of(days, me=False):
    if me: return "admiral"
    for md, rid, _ in RANKS:
        if days >= md and rid != "admiral": return rid
    return "recruit"

cur = json.loads(io.open(CREWJSON, encoding="utf-8").read())
# ricostruisce la lista membri 2026 dal file unificato (people con crew2026),
# preservando gli overlay manuali (board/leave/role/photo/nick/note/link/q)
if "members" in cur:
    members = cur["members"]
else:
    members = [{"id": p["id"], "name": p["name"], **p.get("crew2026", {})}
               for p in cur["people"] if "crew2026" in p]
used_pids = set()
id2pid = {}   # crew_id -> registry pid (per companions)
out = []
TOTAL_DAYS = round(sum(trip_days.values())); TOTAL_NM = sum(trip_nm.values())  # Edoardo
for m in members:
    nm = m["name"]
    if nm.split()[0].lower() in ("edo", "edoardo"):
        st = {"trips": 25, "days": TOTAL_DAYS, "nm": TOTAL_NM, "first": 2011, "last": 2024}; me = True
        tl = trips_list_for(list(trip_year.keys()))   # lo skipper c'e' su tutti i viaggi
    else:
        pid = match(nm); me = False
        if pid: used_pids.add(pid); id2pid[m["id"]] = pid; st = stats(pid); tl = trips_list_for(part.get(pid, []), pid)
        else: st = {"trips": 0, "days": 0, "nm": 0, "first": None, "last": None}; tl = []
    crew2026 = {k: m[k] for k in ("board", "leave", "role", "photo", "nick", "note", "link", "q") if k in m}
    out.append({"id": m["id"], "name": nm, **st, "rank": rank_of(st["days"], me),
                **({"me": True} if me else {}), "trips_list": tl, "crew2026": crew2026})
# alumni: registro non nel crew 2026
for p in part:
    if p in used_pids: continue
    pp = people[p]
    if len((pp.get("nom") or "")) < 2 or not pp.get("cog"): continue  # scarta voci-stub
    st = stats(p); nm = pname(p)
    pid_id = slugify(nm.replace(".", "")) or ("p" + str(p))
    id2pid[pid_id] = p
    out.append({"id": pid_id, "name": nm, **st,
                "rank": rank_of(st["days"]), "trips_list": trips_list_for(part.get(p, []), p)})

# foto taggate per persona (sidecar generato da build_trips.py) -> campo photos
PHOTOTAGS = os.path.join(ROOT, "data", "photo-tags.json")
by_person = {}
if os.path.exists(PHOTOTAGS):
    by_person = json.loads(io.open(PHOTOTAGS, encoding="utf-8").read()).get("by_person", {})
else:
    print("ATTENZIONE: data/photo-tags.json assente -> nessuna foto sui profili. Esegui prima build_trips.py.")
# ritratti scritti a mano (data/crew-bios.json) -> bio; tag di profilo (data/crew-tags.json)
BIOS = os.path.join(ROOT, "data", "crew-bios.json")
bios = json.loads(io.open(BIOS, encoding="utf-8").read()).get("bios", {}) if os.path.exists(BIOS) else {}
TAGS = os.path.join(ROOT, "data", "crew-tags.json")
tagmap = json.loads(io.open(TAGS, encoding="utf-8").read()).get("tags", {}) if os.path.exists(TAGS) else {}
pid2id = {v: k for k, v in id2pid.items()}          # per companions_for
id2name = {x["id"]: x["name"] for x in out}
n_photos = n_bios = n_tags = n_comp = n_avatar = 0
for x in out:
    ph = by_person.get(x["id"], [])
    if ph:
        x["photos"] = ph; n_photos += len(ph)
    b = bios.get(x["id"])
    if b:
        x["bio"] = b; n_bios += 1
    tg = tagmap.get(x["id"])
    if tg:
        x["tags"] = tg; n_tags += 1
    comp = companions_for(id2pid.get(x["id"]))
    if comp:
        x["companions"] = comp; n_comp += 1
    # avatar: ritratto in site/crew/img/<id>.jpg (auto-agganciato per gli alumni,
    # cioe' i membri senza foto nell'overlay crew2026)
    av = os.path.join(ROOT, "site", "crew", "img", x["id"] + ".jpg")
    if os.path.exists(av) and not x.get("crew2026", {}).get("photo"):
        x["photo"] = "crew/img/" + x["id"] + ".jpg"; n_avatar += 1

out.sort(key=lambda x: (-x["days"], -x["trips"]))
data = {"generated_at": "2026-07-11",
        "ranks": {rid: lab for _, rid, lab in RANKS},
        "n_total": len(out),
        "people": out}
io.open(CREWJSON, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=1))
print("crew.json:", len(out), "persone. TOTAL_DAYS(Edo)=", TOTAL_DAYS,
      "| foto:", n_photos, "su", sum(1 for x in out if x.get("photos")), "pers.",
      "| bio:", n_bios, "| tags:", n_tags, "| companions:", n_comp,
      "| trips_list:", sum(1 for x in out if x.get("trips_list")))
rc = collections.Counter(x["rank"] for x in out)
print("distribuzione gradi:", dict(rc))
for x in out[:20]:
    tag = " [2026]" if "crew2026" in x else ""
    print(f"  {x['days']:3d}gg {x['trips']:2d}tr  {x['rank']:8s}  {x['name']}{tag}")
