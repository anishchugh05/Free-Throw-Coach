from dotenv import load_dotenv; load_dotenv()
import json, os, sys
import numpy as np
from pipeline import load, hoop_box_from, all_shots

MODEL = "muse-spark-1.3"

PROMPT = """You are a basketball free-throw coach reviewing ONE practice session.
You get measured data from a fixed side-view camera. Fields:
- entry_angle: degrees at which the ball drops into the rim
- apex_in: how many inches above the rim the ball peaked
- offset_in: where the ball crossed rim height vs the rim centre, in inches
  (positive = short, negative = long). Left/right misses are invisible from the side.
- entry / apex_in are null for shots with a bad fit; ignore those fields there.

Rules:
- Use ONLY the numbers provided. Never invent a measurement or an ideal range.
- Judge the player against their own consistency and their make/miss pattern.
- Name exactly ONE top issue. If the session is too small or too clean to say, set confidence "low" and say so plainly.
- cue: max 12 words, spoken like a coach. drill: one sentence.
- Name one real strength. No jargon, no lists of problems.
- Cues and drills may only address what is measured (arc, entry angle, short/long depth, consistency). Never mention elbow, wrist, follow-through or other body mechanics: the camera does not measure them.
Reply with JSON only, no markdown, exactly:
{"headline": str, "strength": str, "top_issue": {"title": str, "evidence": str, "cue": str, "drill": str},
 "consistency_note": str, "confidence": "low"|"medium"|"high"}"""

def build_report(shots):
    n = len(shots)
    makes = sum(s["made"] for s in shots)
    stat = lambda k, src: ({"mean": round(float(np.mean([s[k] for s in src])), 1),
                            "std": round(float(np.std([s[k] for s in src])), 1)} if src else None)
    ok = [s for s in shots if s["fit_ok"]]
    half = n // 2
    first, second = shots[:half], shots[half:]
    mean = lambda k, src: round(float(np.mean([s[k] for s in src])), 1) if src else None
    misses = [s for s in shots if not s["made"]]
    return {
        "shots": n, "makes": makes, "make_pct": round(100 * makes / n) if n else 0,
        "entry_angle": stat("entry_angle", ok),
        "apex_in": stat("apex_above_rim_in", ok),
        "offset_in": stat("short_in", shots),
        "first_half_vs_second_half": {
            "offset_in_mean": [mean("short_in", first), mean("short_in", second)],
            "entry_angle_mean": [mean("entry_angle", [s for s in first if s["fit_ok"]]),
                                 mean("entry_angle", [s for s in second if s["fit_ok"]])],
            "apex_in_mean": [mean("apex_above_rim_in", [s for s in first if s["fit_ok"]]),
                             mean("apex_above_rim_in", [s for s in second if s["fit_ok"]])],
            "makes": [sum(s["made"] for s in first), sum(s["made"] for s in second)],
        },
        "misses": [{"i": shots.index(s) + 1, "type": s["miss_type"], "offset_in": round(s["short_in"], 1)}
                   for s in misses],
        "per_shot": [{"i": i + 1, "t_s": round(s["t"], 1), "result": "make" if s["made"] else "miss",
                      "entry": round(s["entry_angle"]) if s["fit_ok"] else None,
                      "apex_in": round(s["apex_above_rim_in"]) if s["fit_ok"] else None,
                      "offset_in": round(s["short_in"], 1)} for i, s in enumerate(shots)],
    }

def parse_json(text):
    a, b = text.find("{"), text.rfind("}")
    return json.loads(text[a:b + 1])

def coach(report):
    from openai import OpenAI
    client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
    last = None
    for _ in range(2):
        resp = client.responses.create(
            model=MODEL, reasoning={"effort": "low"},
            input=[{"role": "developer", "content": PROMPT},
                   {"role": "user", "content": json.dumps(report)}])
        try:
            return parse_json(resp.output_text)
        except Exception:
            last = resp.output_text
    raise RuntimeError("could not parse coaching JSON: " + str(last)[:300])

if __name__ == "__main__":
    stem, hoop_stem = sys.argv[1], sys.argv[2]
    shots = all_shots(load(stem, "basketball"), hoop_box_from(load(hoop_stem, "basketball_hoop")))
    report = build_report(shots)
    json.dump(report, open("report.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "per_shot"}, indent=1))
    out = coach(report)
    json.dump(out, open("coaching.json", "w"), indent=1)
    print("\n=== COACHING ===")
    print(json.dumps(out, indent=1))
