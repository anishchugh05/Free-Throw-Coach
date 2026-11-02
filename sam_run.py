from dotenv import load_dotenv; load_dotenv()
import asyncio, os, sys, json, pathlib, collections
from openai import AsyncOpenAI
from meta_sam_parser import parse_responses_stream, video_segmentation_format

PROMPTS = sys.argv[2:] or ["basketball", "basketball hoop"]

async def run(client, file_id, prompt):
    stream = await client.responses.create(
        model="sam-3.1", stream=True, metadata={"include_confidence": "true"},
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_file", "file_id": file_id}]}])
    parsed = parse_responses_stream(stream, video_segmentation_format())
    last = None
    async with parsed:
        async for snap in parsed:
            last = snap
    return [dict(obj=r.object_id, f=r.frame.frame_index, l=r.left, t=r.top,
                 r=r.right, b=r.bottom, c=r.confidence)
            for r in last.records if r.kind == "box"]

def summarize(name, boxes):
    g = collections.defaultdict(list)
    for b in boxes:
        g[b["obj"]].append(b)
    print(f"\n{name}: {len(boxes)} boxes, {len(g)} objects")
    for o, bs in sorted(g.items(), key=lambda kv: -len(kv[1]))[:8]:
        bs.sort(key=lambda b: b["f"]); n = len(bs)
        cx = sum((b["l"] + b["r"]) / 2 for b in bs) / n
        cy = sum((b["t"] + b["b"]) / 2 for b in bs) / n
        w = sum(b["r"] - b["l"] for b in bs) / n
        h = sum(b["b"] - b["t"] for b in bs) / n
        c = sum(b["c"] or 0 for b in bs) / n
        print(f"  obj {o}: {n} frames [{bs[0]['f']}-{bs[-1]['f']}] conf {c:.2f} "
              f"size {w:.0f}x{h:.0f} centre ({cx:.0f},{cy:.0f})")

async def main(path):
    stem = pathlib.Path(path).stem
    pathlib.Path("cache").mkdir(exist_ok=True)
    client = AsyncOpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
    file_id = None
    for p in PROMPTS:
        cf = pathlib.Path(f"cache/{stem}__{p.replace(' ', '_')}.json")
        if not cf.exists():
            if file_id is None:
                file_id = (await client.files.create(file=open(path, "rb"), purpose="user_data")).id
            print("running SAM:", p)
            cf.write_text(json.dumps(await run(client, file_id, p)))
        summarize(p, json.loads(cf.read_text()))

asyncio.run(main(sys.argv[1]))
