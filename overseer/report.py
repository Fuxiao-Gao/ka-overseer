"""Parse the six-line OVERSEER REPORT schema. See protocol.md."""
import re

HEAD = re.compile(r"^OVERSEER REPORT\s+(\S+)\s*$", re.M)
PR_ITEM = re.compile(r"#(\d+)\s*(.*)")
ROUNDS = re.compile(r"\bround\s+(\d+)\b")
THREADS = re.compile(r"\b(\d+)[\s-]threads?\b")
DRIVER = re.compile(r"^(loop|goal|manual)(?:/(\d+)m)?\b")


def _fields(line):
    """'role: a | theme: b' -> {'role': 'a', 'theme': 'b'}"""
    out = {}
    for part in line.split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _pr_items(line):
    prs = {}
    if line.strip().lower() in ("", "-") or line.strip().lower().startswith("none"):
        return prs
    items = []
    for frag in line.split(";"):
        frag = frag.strip()
        if PR_ITEM.match(frag):
            items.append(frag)
        elif items:                      # a semicolon inside the previous item's free text
            items[-1] += "; " + frag
    for item in items:
        m = PR_ITEM.match(item)
        num, raw = int(m.group(1)), m.group(2).strip()
        rounds = ROUNDS.search(raw)
        threads = THREADS.search(raw)
        words = raw.lower().split()
        hold = False if "no-hold" in words else (True if "hold" in words else None)
        prs[num] = {
            "raw": raw,
            "rounds": int(rounds.group(1)) if rounds else None,
            "threads": int(threads.group(1)) if threads else None,
            "hold": hold,
        }
    return prs


def parse_report(text):
    if not text:
        return None
    m = HEAD.search(text)
    if not m:
        return None
    r = {"session": m.group(1), "role": None, "theme": None, "driver": None,
         "cadence_min": None, "mode": None, "prs": {}, "status": None,
         "needs": None, "status_detail": None, "rules": None, "note": None}
    body = text[m.end():]
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("<"):
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "prs":
            r["prs"] = _pr_items(value)
        elif key == "status":
            m2 = re.match(r"\s*([A-Za-z_-]+)\s*:?\s*(.*)$", value)
            token, rest = (m2.group(1), m2.group(2)) if m2 else (value, "")
            r["status"] = token.lower().replace("_", "-")
            if r["status"].startswith("waiting-") and r["status"] != "waiting-review":
                r["status"] = "waiting-human"          # waiting-brian, waiting-user, ... all mean the same stall
            rest = rest.strip()
            if r["status"] == "waiting-human":
                r["needs"] = rest or None
            else:
                r["status_detail"] = rest or None
        elif key == "rules":
            digits = re.search(r"\d+", value)
            r["rules"] = int(digits.group()) if digits else None
        elif key == "note":
            r["note"] = value or None
        elif key in ("role", "theme", "driver", "mode"):
            f = _fields(line)
            for k in ("role", "theme", "mode"):
                if k in f:
                    r[k] = f[k]
            if "driver" in f:
                d = DRIVER.match(f["driver"])
                if d:
                    r["driver"] = d.group(1)
                    r["cadence_min"] = int(d.group(2)) if d.group(2) else None
                else:
                    r["driver"] = f["driver"]
    return r
