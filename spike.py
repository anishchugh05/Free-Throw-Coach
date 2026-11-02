from dotenv import load_dotenv; load_dotenv()
import asyncio, os, sys, time
from openai import AsyncOpenAI
from meta_sam_parser import parse_responses_stream, video_segmentation_format

async def main(path, prompt):
    c = AsyncOpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
    f = await c.files.create(file=open(path, "rb"), purpose="user_data")
    print("uploaded", f.id)
    last = None
    for part in ({"type": "input_file", "file_id": f.id},
                 {"type": "input_video", "file_id": f.id}):
        try:
            t = time.time()
            stream = await c.responses.create(
                model="sam-3.1", stream=True,
                metadata={"include_confidence": "true"},
                input=[{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": prompt}, part]}])
            parsed = parse_responses_stream(stream, video_segmentation_format())
            async with parsed:
                async for snap in parsed:
                    last = snap
            print("OK with", part["type"], f"{time.time()-t:.0f}s")
            break
        except Exception as e:
            print("FAILED", part["type"], repr(e)[:300])
    if last:
        print(len(last.records), "records")
        print(last.records[0])

asyncio.run(main(sys.argv[1], sys.argv[2]))
