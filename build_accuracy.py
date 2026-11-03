"""Score clips against hand logs and write static/accuracy.json for the site.

  python build_accuracy.py full:spike:shot_log.txt [more clips as stem:hoop_stem:logfile ...]

Optional accuracy_notes.json: {"<stem>": {"label": "...", "tuned": true, "errors": {"<log seconds>": "why"}}}
"""
import json, pathlib, re, sys
from pipeline import load, hoop_box_from, all_shots


def parse_log(path):
    out = []
    for line in open(path):
        m = re.search(r"(make|miss)\D+(\d+)[.:](\d+)", line, re.I)
        if m:
            out.append((m.group(1).lower(), int(m.group(2)) * 60 + int(m.group(3))))
    return out


def score(stem, hoop_stem, logfile):
    shots = all_shots(load(stem, "basketball"), hoop_box_from(load(hoop_stem, "basketball_hoop")))
    log = parse_log(logfile)
    used, rows = set(), []
    for truth, tl in log:
        cand = [(abs(tl - s["t"] - 0.7), i) for i, s in enumerate(shots)
                if i not in used and -0.5 <= tl - s["t"] <= 3.5]
        if not cand:
            rows.append((truth, tl, None)); continue
        _, i = min(cand); used.add(i); rows.append((truth, tl, shots[i]))
    found = [r for r in rows if r[2] is not None]
    conf = {"make_make": 0, "make_miss": 0, "miss_make": 0, "miss_miss": 0}   # truth_detected
    errors = []
    for truth, tl, s in found:
        det = "make" if s["made"] else "miss"
        conf[f"{truth}_{det}"] += 1
        if det != truth:
            errors.append(dict(t=tl, truth=truth, detected=det, offset_in=round(s["short_in"], 1)))
    missed = [dict(t=tl, truth=truth) for truth, tl, s in rows if s is None]
    return dict(stem=stem, logged=len(log), found=len(found), extra=len(shots) - len(used),
                correct=sum(1 for t, _, s in found if (("make" if s["made"] else "miss") == t)),
                confusion=conf, errors=errors, not_found=missed,
                bad_fits=sum(not s["fit_ok"] for s in shots))


if __name__ == "__main__":
    notes_p = pathlib.Path("accuracy_notes.json")
    notes = json.loads(notes_p.read_text()) if notes_p.exists() else {}
    clips = []
    for spec in sys.argv[1:]:
        stem, hoop, log = spec.split(":")
        r = score(stem, hoop, log)
        n = notes.get(stem, {})
        r["label"] = n.get("label", stem)
        r["tuned"] = bool(n.get("tuned", False))
        for e in r["errors"]:
            e["note"] = n.get("errors", {}).get(str(e["t"]), "")
        clips.append(r)
        print(stem, f"{r['correct']}/{r['found']} correct, found {r['found']}/{r['logged']}, extra {r['extra']}")
    out = pathlib.Path("static/accuracy.json"); out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dict(clips=clips), indent=1))
    print("wrote", out)
