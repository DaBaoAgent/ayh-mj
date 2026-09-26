import asyncio, json, sys
from pathlib import Path
from shazamio import Shazam
async def m():
    sh = Shazam()
    r = await sh.recognize(str(Path(sys.argv[1])))
    print("KEYS:", list(r.keys()))
    print(json.dumps(r, ensure_ascii=False)[:1200])
asyncio.run(m())
