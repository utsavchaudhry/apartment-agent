"""Search settings.

Defaults live in defaults.json next to this file. Your own values live in
$DATA_DIR/settings.json, which the dashboard writes. Every key is exposed here
upper-cased, so `max_rent_warm` is read as `config.MAX_RENT_WARM`.

Call load() again after settings.json changes to pick up the new values.
"""
import os, json, copy, secrets

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(os.path.dirname(HERE), "data")
DEFAULTS_PATH = os.path.join(HERE, "defaults.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "plz_commute" \
                and k != "station_commute":
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def defaults():
    with open(DEFAULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def read():
    """Effective settings: defaults overlaid with settings.json."""
    s = defaults()
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s = _merge(s, json.load(f))
    # First run: invent a private ntfy topic so push works out of the box.
    if not s.get("ntfy_topic"):
        s["ntfy_topic"] = "apartment-agent-" + secrets.token_urlsafe(9).lower().replace("_", "x").replace("-", "x")
        write(s)
    return s


def write(s):
    """Store only what differs from defaults.json, so improved defaults (a new
    block term, a fixed commute time) still reach anyone who has saved before."""
    base = defaults()
    s = {k: v for k, v in s.items() if base.get(k) != v}
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS_PATH)


def load():
    g = globals()
    for k, v in read().items():
        g[k.upper()] = v
    # postcode -> (area label, minutes)
    g["PLZ_COMMUTE"] = {k: tuple(v) for k, v in g["PLZ_COMMUTE"].items()}
    g["ESTIMATE_WARM_FOR"] = tuple(g["ESTIMATE_WARM_FOR"])


load()
