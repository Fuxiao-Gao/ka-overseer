"""Render state.json (+ roster.json) to a static dashboard. Ages are computed client-side."""
import argparse
import html
import json
import re
import sys
from pathlib import Path

import state as S
from config import CFG
REPO = CFG["repo"]

PR_URL = "https://github.com/" + REPO + "/pull/{n}"
PR_REF = re.compile(r"#(\d+)")

# dataviz status palette; every status also carries an icon + word, never colour alone.
CSS = """
:root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e6e5e1;
--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--critical:#d03b3b;--band:#fbe9e9;--goodband:#e9f7e9;--tint:#f4f3f0}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--line:#33332f;--band:#3a1f1f;--goodband:#1f2f1f;--tint:#232320}}
body{margin:0;padding:16px 20px;background:var(--surface);color:var(--ink);font:13px/1.4 -apple-system,Helvetica,Arial,sans-serif}
h1{font-size:16px;margin:0 0 8px}h2{font-size:13px;color:var(--ink2);margin:18px 0 6px;text-transform:uppercase;letter-spacing:.04em}
.attention{border-radius:6px;padding:8px 12px;margin-bottom:6px}
.attention.red{background:var(--band);border-left:4px solid var(--critical)}
.attention.green{background:var(--goodband);border-left:4px solid var(--good);color:var(--ink2)}
.attention.note{background:var(--tint);border-left:4px solid var(--muted);color:var(--ink2)}
.attention table{margin:0}
table{border-collapse:collapse;width:100%}th{text-align:left;color:var(--muted);font-weight:500;padding:4px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:4px 8px;border-bottom:1px solid var(--line);white-space:nowrap;max-width:28em;overflow:hidden;text-overflow:ellipsis;vertical-align:top}
tr.gone td{color:var(--muted)}tr.waiting td:first-child{border-left:4px solid var(--critical)}
.s-good{color:var(--good)}.s-warn{color:var(--serious)}.s-bad{color:var(--critical)}.muted{color:var(--muted)}
.cap{color:var(--critical);font-weight:600}.stale{color:var(--serious);font-weight:600}
a{color:inherit}footer{margin-top:18px;color:var(--muted)}
"""

JS = """
function age(ts){if(!ts)return '—';const d=(Date.now()-Date.parse(ts))/1000;if(d<0)return 'in '+age(new Date(Date.now()+d*1000).toISOString());
if(d<3600)return Math.floor(d/60)+'m';if(d<86400)return Math.floor(d/3600)+'h'+Math.floor((d%3600)/60)+'m';return Math.floor(d/86400)+'d'+Math.floor((d%86400)/3600)+'h';}
function tick(){document.querySelectorAll('[data-ts]').forEach(e=>{e.textContent=age(e.dataset.ts);
const lim=parseFloat(e.dataset.stale||'0');if(lim&&(Date.now()-Date.parse(e.dataset.ts))/60000>lim)e.classList.add('stale');});}
tick();setInterval(tick,15000);
"""

ROSTER_ICON = {"busy": "● busy", "shell": "▶ shell", "idle": "○ idle", "waiting": "⏸ waiting", "gone": "✕ gone", None: "—"}
CHECK_ICON = {"green": ("✓ green", "s-good"), "red": ("✗ red", "s-bad"), "pending": ("… pending", "s-warn"), "none": ("– none", "muted"), None: ("—", "muted")}
STATUS_ICON = {"working": "▸ working", "waiting-human": "⚑ waiting-human", "waiting-review": "◷ waiting-review",
               "idle": "○ idle", "gone": "✕ gone", None: "—"}


def e(x):
    return html.escape("" if x is None else str(x))


def pr_link(n):
    return f'<a href="{PR_URL.format(n=n)}">#{n}</a>'


def L(x):
    """Escape, then turn every #NNNN into a link to that PR."""
    return PR_REF.sub(lambda m: pr_link(m.group(1)), e(x))


def ts(x, stale_min=None):
    if not x:
        return "—"
    extra = f' data-stale="{stale_min}"' if stale_min else ""
    return f'<span data-ts="{e(x)}"{extra}>{e(x)}</span>'


def yn(v):
    return "yes" if v else ("no" if v is False else "—")


NOTE_KINDS = {"gone-question"}     # shown, but nothing can answer it: no red band


def _attention_table(items, cls):
    rows = "".join(
        f"<tr><td>{e(i['session'])}</td><td>{pr_link(i['pr']) if i['pr'] else '—'}</td>"
        f"<td>{ts(i['since'])}</td><td>{e(i['kind'])}</td><td title=\"{e(i['what'])}\">{L(i['what'])}</td></tr>"
        for i in items)
    return (f'<div class="attention {cls}"><table><tr><th>session</th><th>PR</th><th>for</th><th>kind</th><th>what</th></tr>'
            f"{rows}</table></div>")


def _attention(state):
    items = sorted(state["attention"], key=lambda i: i["since"])
    loud = [i for i in items if i["kind"] not in NOTE_KINDS]
    notes = [i for i in items if i["kind"] in NOTE_KINDS]
    head = _attention_table(loud, "red") if loud else '<div class="attention green">✓ Nothing is waiting on you.</div>'
    return head + (_attention_table(notes, "note") if notes else "")


def _sessions(state, roster):
    live = {a["name"]: a["status"] for a in (roster or [])}
    out = []
    for name in sorted(state["sessions"]):
        r = state["sessions"][name]
        rs = r["roster_status"]
        if roster is not None:
            rs = live.get(name, "gone" if rs else None)
        if rs == "gone" and r["roster_status"] == "gone" and S.is_live(state, name):
            rs = None                    # reported since it left; the roster has not caught up
        cls = "gone" if rs == "gone" else ("waiting" if rs == "waiting" else "")
        cadence = r["cadence_min"]
        stale = cadence * 2 if cadence else None
        driver = f"{r['driver']}/{cadence}m" if r["driver"] and cadence else (r["driver"] or "—")
        prs = " ".join(pr_link(n) for n in r["prs"]) or "—"
        out.append(
            f'<tr class="row {cls}"><td>{e(name)}</td><td>{e(r["role"] or "—")}</td><td>{L(r["theme"] or "—")}</td>'
            f"<td>{e(driver)}</td><td>{ROSTER_ICON.get(rs, e(rs))}</td><td>{STATUS_ICON.get(r['status'], e(r['status']))}</td>"
            f"<td>{prs}</td><td>{ts(r['last_report'], stale)}</td><td>{ts(r['last_activity'])}</td>"
            f"<td>{e(r['rules_ack'] or '—')}</td><td title=\"{e(r['needs'] or r['status_detail'] or r['note'])}\">{L(r['needs'] or r['status_detail'] or r['note'] or '')}</td></tr>")
    return ("<table><tr><th>session</th><th>role</th><th>theme</th><th>driver</th><th>roster</th><th>reported</th>"
            "<th>PRs</th><th>last report</th><th>last activity</th><th>rules</th><th>needs / note</th></tr>"
            + "".join(out) + "</table>")


def _pr_sort_key(item):
    n, p = item
    open_ = 0 if p.get("state") in S.OPEN_PR_STATES else 1
    gate = (p.get("unresolved_threads") or 0) + (0 if p.get("checks") == "green" else 1)
    return (open_, gate, -int(n))


def _prs(state):
    out = []
    for n, p in sorted(state["prs"].items(), key=_pr_sort_key):
        if p.get("state") not in S.OPEN_PR_STATES:
            continue
        chk, chk_cls = CHECK_ICON.get(p.get("checks"), ("—", "muted"))
        rounds = p.get("rounds")
        rounds_html = f'<span class="cap">{rounds}</span>' if (rounds or 0) >= 6 else e(rounds if rounds is not None else "—")
        title = f'<a href="{e(p["url"]) if p.get("url") else PR_URL.format(n=n)}">#{n}</a> {e(p["title"] or "")}'
        err = f' title="snapshot error: {e(p["snapshot_error"])}"' if p.get("snapshot_error") else ""
        out.append(
            f"<tr{err}><td>{title}</td><td>{e(p['owner'] or '—')}</td><td>{e(p['mergeable'] or '—')}</td>"
            f'<td class="{chk_cls}">{chk}</td><td>{e(p["unresolved_threads"] if p["unresolved_threads"] is not None else "—")}</td>'
            f'<td>{rounds_html}</td><td class="muted">{e(p["advisory_rounds"] if p["advisory_rounds"] is not None else "—")}</td>'
            f"<td>{yn(p['hold'])}</td><td>{yn(p['lgtm'])}</td><td>{yn(p['approved'])}</td>"
            f"<td>{e(', '.join(p['reviewers']) or '—')}</td><td>{ts(p['last_activity'])}</td>"
            f"<td title=\"{e(p['drift'])}\">{L(p['drift'] or '')}</td></tr>")
    return ("<table><tr><th>PR</th><th>owner</th><th>mergeable</th><th>checks</th><th>threads</th><th>rounds</th>"
            "<th>kyber</th><th>hold</th><th>lgtm</th><th>approved</th><th>reviewers</th><th>activity</th><th>drift</th></tr>"
            + "".join(out) + "</table>")


def render(state, roster, now):
    ov = state.get("overseer") or {}
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="60">
<title>Overseer</title><style>{CSS}</style></head><body>
<h1>Overseer</h1>
{_attention(state)}
<h2>Sessions</h2>{_sessions(state, roster)}
<h2>PRs</h2>{_prs(state)}
<footer>Rendered {ts(now)} ago · Rules v{e(state.get('rules_version'))} · Overseer {e(ov.get('session') or '—')} tick {e(ov.get('tick'))} · next wake {ts(ov.get('next_wake')) if ov.get('next_wake') else '—'}</footer>
<script>{JS}</script></body></html>"""


def main(argv=None):
    here = Path(__file__).parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(here / "state.json"))
    ap.add_argument("--roster", default=str(here / "roster.json"))
    ap.add_argument("--out", default=str(here / "dashboard.html"))
    a = ap.parse_args(argv)
    state = S.load_state(a.state)
    roster = None
    if Path(a.roster).exists():
        try:
            roster = json.loads(Path(a.roster).read_text()).get("sessions")
        except ValueError:
            roster = None
    S.write_atomic(a.out, render(state, roster, S.now_iso()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
