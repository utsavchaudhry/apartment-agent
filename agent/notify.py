"""Push a match to your phone (and optionally your inbox). Free.

Phone push uses ntfy.sh: no account, no API key. Install the "ntfy" app
(Android/iOS) and subscribe to the topic shown on the dashboard's Settings page.
ntfy can also forward to e-mail, but only with a free account token set.
"""
import urllib.request
import config


def push(title, body, url=None, email=False, priority="high"):
    """ntfy push. email=True also forwards to the configured address."""
    topic = getattr(config, "NTFY_TOPIC", "")
    if not topic:
        return False
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": priority,
        "Tags": "house",
    }
    if url:
        headers["Click"] = url
    token = getattr(config, "NTFY_TOKEN", "")
    address = getattr(config, "NOTIFY_EMAIL", "")
    # ntfy.sh refuses e-mail forwarding for anonymous publishers (error 40053).
    if email and address and token:
        headers["Email"] = address
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request("https://ntfy.sh/" + topic,
                                 data=body.encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status < 300
    except Exception:
        return False


def announce(rec, email=True):
    """Fire every channel for one new match."""
    title = f"{rec.get('price')}€ · {rec.get('area') or '?'}"
    body = (f"{rec.get('title','')}\n"
            f"{rec.get('sqm') or '?'} m² · ~{rec.get('commute') or '?'} min commute\n"
            f"{rec.get('url','')}")
    return push(title, body, url=rec.get("url"), email=email)
