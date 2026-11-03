"""python coach.py full spike   -> shots -> session report -> Muse Spark coaching (JSON)."""
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
- shooter (optional) comes from tracking the player's body box, in % of the player's own body height:
  reach_pct = how high the arms/ball reach above the head at the top of the shot (higher = more extension),
  tempo_s = seconds from the start of the lift to full reach, stance_drift_pct = how much the back edge of the
  body moves between shots (std/range; small = same stance every time), between_shots_s = time between shots.
  Use these only as consistency signals. Do not convert them to inches or call them good or bad in absolute terms.

Rules:
- Use ONLY the numbers provided. Never invent a measurement or an ideal range.
- Judge the player against their own consistency and their make/miss pattern.
- Name exactly ONE top issue. If the session is too small or too clean to say, set confidence "low" and say so plainly.
- cue: max 12 words, spoken like a coach. drill: one sentence.
- Name one real strength (it may come from the shooter routine metrics). No jargon, no lists of problems.
Reply with JSON only, no markdown, exactly:
{"headline": str, "strength": str, "top_issue": {"title": str, "evidence": str, "cue": str, "drill": str},
 "consistency_note": str, "confidence": "low"|"medium"|"high"}"""


def build_report(shots, shooter=None):
    n = len(shots)
    makes = sum(s["made"] for s in shots)
    stat = lambda k, src: ({"mean": round(float(np.mean([s[k] for s in src])), 1),
                            "std": round(float(np.std([s[k] for s in src])), 1)} if src else None)
    ok = [s for s in shots if s["fit_ok"]]
    half = n // 2
    first, second = shots[:half], shots[half:]
    mean = lambda k, src: round(float(np.mean([s[k] for s in src])), 1) if src else None
    misses = [s for s in shots if not s["made"]]
    rep = {
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
    if shooter:
        rep["shooter"] = shooter
    return rep


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
        except Exception as e:
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


ASK_PROMPT = """You are the free-throw coach for ONE player, answering a question about THEIR practice session.
The JSON below is everything we measured. Fields:
- shots[]: i = shot number, t = seconds into the video, made, miss_type (short/long), entry = entry angle in degrees,
  apex_in = inches the arc peaked above the rim, short_in = where the ball crossed rim height (positive = short,
  negative = long), reach_pct / tempo_s = shooter routine numbers (percent of body height / seconds). null = not measured.
- report: session totals and averages. shooter: routine consistency. coaching: the verdict already shown to the player.
Rules:
- Use ONLY this data. Cite shot numbers like #7. Never invent a measurement.
- Left/right misses, elbow, wrist, follow-through, grip, mental state are NOT measured. If asked, say we can't see
  that from a side camera, then answer the closest thing the data does show.
- If the question is not about this session or free-throw shooting, say you only coach this session.
- Plain text, max 70 words, no markdown, no lists, spoken like a coach. No medical advice."""


def ask(data, question, history=None):
    from openai import OpenAI
    client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
    turns = ""
    for h in (history or [])[-3:]:
        turns += f"Player: {str(h.get('q', ''))[:300]}\nCoach: {str(h.get('a', ''))[:600]}\n"
    user = (turns + "Player: " if turns else "") + question[:300]
    resp = client.responses.create(
        model=MODEL, reasoning={"effort": "low"},
        input=[{"role": "developer", "content": ASK_PROMPT + "\n\nSESSION DATA:\n" + json.dumps(data)},
               {"role": "user", "content": user}])
    text = (resp.output_text or "").strip()
    if not text:
        raise RuntimeError("empty answer")
    return text[:900]
