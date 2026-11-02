"""Thin wrapper around Meta Model API SAM 3.1 (video segmentation, streamed)."""
import asyncio, os
from openai import AsyncOpenAI
from meta_sam_parser import parse_responses_stream, video_segmentation_format


def make_client():
    return AsyncOpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])


async def segment(client, path, prompt):
    """Upload `path`, run SAM 3.1 with a short text prompt, return per-frame box dicts."""
    f = await client.files.create(file=open(path, "rb"), purpose="user_data")
    stream = await client.responses.create(
        model="sam-3.1", stream=True, metadata={"include_confidence": "true"},
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_file", "file_id": f.id}]}])
    parsed = parse_responses_stream(stream, video_segmentation_format())
    last = None
    async with parsed:
        async for snap in parsed:
            last = snap
    if last is None:
        return []
    return [dict(obj=r.object_id, f=r.frame.frame_index, l=r.left, t=r.top,
                 r=r.right, b=r.bottom, c=r.confidence)
            for r in last.records if r.kind == "box"]
