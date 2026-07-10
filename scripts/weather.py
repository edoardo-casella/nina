"""Meteo: Open-Meteo (vento + mare) con cache locale, e cross-check Aeronautica Militare.

Open-Meteo e' gratuito e non richiede API key (limite ~10.000 richieste/giorno).
I modelli d'onda hanno risoluzione ~5 km: sottocosta sono indicativi.
NON usare come unica fonte per decisioni di sicurezza.
"""
from __future__ import annotations
import hashlib, json, sys, tempfile, time, urllib.request, urllib.parse
from pathlib import Path

# Windows: la console usa cp1252 e non regge il simbolo dei gradi.
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

CACHE = Path(tempfile.gettempdir()) / "sailing_wx_cache"
CACHE.mkdir(parents=True, exist_ok=True)
TTL_S = 3600  # 1 ora

FORECAST = "https://api.open-meteo.com/v1/forecast"
MARINE = "https://marine-api.open-meteo.com/v1/marine"

AM_BULLETIN = "https://www.meteoam.it/it/mare"
AM_NOTE = (
    "CROSS-CHECK OBBLIGATORIO: confrontare con il bollettino del mare "
    "dell'Aeronautica Militare (meteoam.it/it/mare) e con l'avviso di burrasca. "
    "In caso di discordanza, prevale il bollettino ufficiale."
)


def _get(url: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{q}"
    # hash() e' randomizzato per processo: serve un digest stabile o la cache non si riusa mai
    key = CACHE / (hashlib.sha1(full.encode()).hexdigest() + ".json")
    if key.exists() and time.time() - key.stat().st_mtime < TTL_S:
        return json.loads(key.read_text(encoding="utf-8"))
    # met.no rifiuta le richieste senza User-Agent identificativo
    req = urllib.request.Request(full, headers={
        "User-Agent": "nina-sailing-agent/1.0 github.com/edoardo-casella/nina"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    key.write_text(json.dumps(data), encoding="utf-8")
    return data


def wind(lat: float, lon: float, days: int = 5, model: str = "ecmwf_ifs025") -> dict:
    """Vento orario: velocita' (kn), direzione (da cui viene), raffiche, cielo."""
    return _get(FORECAST, {
        "latitude": lat, "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,temperature_2m,relative_humidity_2m,weather_code",
        "wind_speed_unit": "kn", "timezone": "Europe/Rome",
        "forecast_days": days, "models": model,
    })


def sea(lat: float, lon: float, days: int = 5) -> dict:
    """Onda oraria + temperatura superficiale del mare (SST)."""
    return _get(MARINE, {
        "latitude": lat, "longitude": lon,
        "hourly": "wave_height,wave_direction,wave_period,wind_wave_height,sea_surface_temperature",
        "timezone": "Europe/Rome", "forecast_days": days,
    })


def combined(lat: float, lon: float, days: int = 5) -> list[dict]:
    """Serie oraria unificata [{time, tws, twd, gust, wave, wave_dir, rain}, ...]"""
    w = wind(lat, lon, days)["hourly"]
    try:
        s = sea(lat, lon, days)["hourly"]
    except Exception:
        s = {}
    out = []
    for i, t in enumerate(w["time"]):
        row = {
            "time": t,
            "tws": w["wind_speed_10m"][i],
            "twd": w["wind_direction_10m"][i],
            "gust": w["wind_gusts_10m"][i],
            "rain": w["precipitation"][i],
            "temp": (w.get("temperature_2m") or [None] * len(w["time"]))[i],
            "rh": (w.get("relative_humidity_2m") or [None] * len(w["time"]))[i],
            "wmo": (w.get("weather_code") or [None] * len(w["time"]))[i],
        }
        if s:
            try:
                j = s["time"].index(t)
                row["wave"] = s["wave_height"][j]
                row["wave_dir"] = s["wave_direction"][j]
                row["wave_period"] = s["wave_period"][j]
                sst = (s.get("sea_surface_temperature") or [None] * len(s["time"]))[j]
                row["sst"] = sst
            except (ValueError, IndexError):
                pass
        out.append(row)
    return out


def _metno_event(p: dict, key: str) -> tuple[str | None, float | None]:
    ev = p.get(key) or {}
    t = ev.get("time")
    az = ev.get("azimuth")
    return (t[11:16] if t else None), (round(az) if az is not None else None)


def sun_moon(lat: float, lon: float, day: str, days: int = 6) -> list[dict]:
    """Effemeridi per `days` giorni da `day` via met.no (gratuito, User-Agent):
    alba/tramonto di sole e luna con AZIMUT (gradi veri), fase lunare.

    moon_deg: 0 = nuova, 90 = primo quarto, 180 = piena, 270 = ultimo quarto.
    Ogni campo puo' essere None (la luna non sorge/tramonta ogni giorno, o
    met.no non raggiungibile): chi consuma deve reggerlo. Fallback alba e
    tramonto da Open-Meteo se met.no /sun non risponde.
    """
    import datetime as dt
    d0 = dt.date.fromisoformat(day)
    end = (d0 + dt.timedelta(days=days - 1)).isoformat()
    try:
        om_sun = _get(FORECAST, {
            "latitude": lat, "longitude": lon, "daily": "sunrise,sunset",
            "timezone": "Europe/Rome", "start_date": day, "end_date": end,
        })["daily"]
    except Exception:
        om_sun = None

    out = []
    for i in range(days):
        date = (d0 + dt.timedelta(days=i)).isoformat()
        row = {"date": date, "sunrise": None, "sunset": None, "sunrise_az": None,
               "sunset_az": None, "moonrise": None, "moonset": None,
               "moonrise_az": None, "moonset_az": None, "moon_deg": None}
        try:
            p = _get("https://api.met.no/weatherapi/sunrise/3.0/sun",
                     {"lat": lat, "lon": lon, "date": date, "offset": "+02:00"})["properties"]
            row["sunrise"], row["sunrise_az"] = _metno_event(p, "sunrise")
            row["sunset"], row["sunset_az"] = _metno_event(p, "sunset")
        except Exception:
            pass
        if row["sunrise"] is None and om_sun and date in om_sun["time"]:
            j = om_sun["time"].index(date)
            row["sunrise"], row["sunset"] = om_sun["sunrise"][j][11:16], om_sun["sunset"][j][11:16]
        try:
            p = _get("https://api.met.no/weatherapi/sunrise/3.0/moon",
                     {"lat": lat, "lon": lon, "date": date, "offset": "+02:00"})["properties"]
            row["moonrise"], row["moonrise_az"] = _metno_event(p, "moonrise")
            row["moonset"], row["moonset_az"] = _metno_event(p, "moonset")
            row["moon_deg"] = p.get("moonphase")
        except Exception:
            pass
        out.append(row)
    return out


DAILY_VARS = ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
              "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,"
              "wind_direction_10m_dominant")

SEA_DAILY_VARS = ("wave_height_max,wave_direction_dominant,wave_period_max,"
                  "sea_surface_temperature_max,sea_surface_temperature_min")


def _clamp_horizon(end: str, max_days: int) -> str:
    """L'API rifiuta le date oltre l'orizzonte del modello: meglio troncare
    la richiesta che farla fallire tutta."""
    import datetime as dt
    lim = (dt.date.today() + dt.timedelta(days=max_days)).isoformat()
    return min(end, lim)


def daily_at(points: list[tuple[float, float]], start: str, end: str,
             model: str | None = None) -> list[dict]:
    """Previsione giornaliera per una LISTA di coordinate (una chiamata sola).
    Ritorna una lista di risposte nello stesso ordine dei punti.
    Orizzonte forecast ~16 giorni (best_match): end viene troncato."""
    params = {
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
        "daily": DAILY_VARS, "wind_speed_unit": "kn",
        "timezone": "Europe/Rome", "start_date": start,
        "end_date": _clamp_horizon(end, 15),
    }
    if model:
        params["models"] = model
    data = _get(FORECAST, params)
    return data if isinstance(data, list) else [data]


def sea_daily(points: list[tuple[float, float]], start: str, end: str) -> list[dict]:
    """Onda giornaliera (max) per una LISTA di coordinate, una chiamata sola.
    Orizzonte marine ~8 giorni: end viene troncato a oggi+7."""
    data = _get(MARINE, {
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
        "daily": SEA_DAILY_VARS,
        "timezone": "Europe/Rome", "start_date": start,
        "end_date": _clamp_horizon(end, 7),
    })
    return data if isinstance(data, list) else [data]


def ensemble_spread(lat: float, lon: float, days: int = 3) -> dict:
    """Confronta due modelli: se divergono molto, la previsione e' poco affidabile."""
    a = wind(lat, lon, days, "ecmwf_ifs025")["hourly"]["wind_speed_10m"]
    b = wind(lat, lon, days, "icon_eu")["hourly"]["wind_speed_10m"]
    n = min(len(a), len(b))
    diffs = [abs(a[i] - b[i]) for i in range(n)]
    mean = sum(diffs) / n if n else 0
    return {"mean_spread_kn": round(mean, 1), "max_spread_kn": round(max(diffs), 1) if diffs else 0,
            "confidence": "alta" if mean < 3 else ("media" if mean < 6 else "bassa")}


if __name__ == "__main__":
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    for r in combined(lat, lon, 2)[:24]:
        print(f"{r['time']}  {r['tws']:>5.1f} kn da {r['twd']:>3.0f}°  raffica {r['gust']:>5.1f}  onda {r.get('wave','-')} m")
    print("\n" + AM_NOTE)
