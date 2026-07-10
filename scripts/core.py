"""Core del sailing-agent: stato del viaggio, geodesia, polare barca.

Tutto lo stato vive in data/voyage.json (single source of truth).
"""
from __future__ import annotations
import json, math, os, sys, datetime as dt
from pathlib import Path

# Windows: la console usa cp1252 e non regge frecce/emoji dei report.
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
VOYAGE = Path(os.environ.get("SAILING_VOYAGE", DATA / "voyage.json"))
ANCHORAGES = DATA / "anchorages.json"


# ---------- stato ----------
def load(path: Path = VOYAGE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(v: dict, path: Path = VOYAGE) -> None:
    v["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(v, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def anchorages() -> list[dict]:
    with open(ANCHORAGES, encoding="utf-8") as f:
        return json.load(f)["anchorages"]


def find_wp(v: dict, name: str) -> dict:
    key = name.strip().lower()
    for wp in v["waypoints"]:
        if wp["name"].lower() == key or wp.get("id", "").lower() == key:
            return wp
    raise KeyError(f"Waypoint non trovato: {name}")


# ---------- geodesia ----------
R_NM = 3440.065  # raggio terrestre in miglia nautiche


def haversine_nm(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_NM * math.asin(math.sqrt(d))


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Rotta vera iniziale da a verso b, in gradi 0-360."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def norm180(deg: float) -> float:
    """Riporta un angolo in [-180, 180]."""
    return (deg + 180) % 360 - 180


def twa(twd: float, cog: float) -> float:
    """Angolo di vento reale: 0 = vento in prua, 180 = in poppa. Sempre positivo."""
    return abs(norm180(twd - cog))


def in_sector(deg: float, start: float, end: float) -> bool:
    """True se deg cade nel settore start->end percorso in senso orario."""
    span = (end - start) % 360
    off = (deg - start) % 360
    return off <= span


# ---------- polare ----------
class Polar:
    """Polare in formato .pol/.csv: prima riga = TWS, prima colonna = TWA."""

    def __init__(self, path: Path):
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for sep in (";", "\t", ","):
                if sep in line:
                    rows.append([c.strip() for c in line.split(sep)])
                    break
        self.tws = [float(x) for x in rows[0][1:]]
        self.twa = [float(r[0]) for r in rows[1:]]
        self.table = [[float(c) for c in r[1:]] for r in rows[1:]]
        self.meta = {"path": str(path)}

    @staticmethod
    def _interp(x, xs, ys):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                t = (x - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        return ys[-1]

    def speed(self, twa_deg: float, tws_kn: float) -> float:
        """Velocità barca stimata (kn) per TWA/TWS, con interpolazione bilineare."""
        twa_deg = abs(norm180(twa_deg)) if twa_deg > 180 else abs(twa_deg)
        per_twa = [self._interp(tws_kn, self.tws, row) for row in self.table]
        return round(self._interp(twa_deg, self.twa, per_twa), 2)

    @property
    def min_twa(self) -> float:
        return self.twa[0]

    def best_upwind(self, tws_kn: float) -> tuple[float, float]:
        """Angolo di bolina ottimo e VMG (velocità guadagnata verso vento) in kn.

        Sotto min_twa la barca non ci arriva: deve bordeggiare. La velocità
        utile verso la destinazione è speed * cos(TWA), non speed.
        """
        cands = [(t, self.speed(t, tws_kn) * math.cos(math.radians(t)))
                 for t in self.twa if t <= 90]
        return max(cands, key=lambda c: c[1])

    def best_downwind(self, tws_kn: float) -> tuple[float, float]:
        """Angolo di poppa ottimo e VMG. In poppa piena il cat strambata."""
        cands = [(t, self.speed(t, tws_kn) * abs(math.cos(math.radians(t))))
                 for t in self.twa if t >= 120]
        return max(cands, key=lambda c: c[1])


def polar(v: dict | None = None) -> Polar:
    v = v or load()
    return Polar(DATA / "polars" / v["boat"]["polar_file"])


# ---------- equipaggio ----------
def parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def nights_aboard(member: dict) -> int:
    return (parse_date(member["leave"]) - parse_date(member["board"])).days


def aboard_on(v: dict, day: str) -> list[dict]:
    """Chi è a bordo la notte del giorno `day` (YYYY-MM-DD)."""
    d = parse_date(day)
    return [m for m in v["crew"] if parse_date(m["board"]) <= d < parse_date(m["leave"])]


if __name__ == "__main__":
    v = load()
    print(f"Viaggio: {v['name']}  |  {len(v['crew'])} persone  |  {len(v['waypoints'])} waypoint")
    p = polar(v)
    print(f"Polare {v['boat']['model']}: TWA 90 / TWS 14 -> {p.speed(90, 14)} kn")
