"""Turn out/walkthrough.webm into two MP4s in deliverables/.

  quoteline-walkthrough.mp4        with a caption strip below the app, one caption per scene
  quoteline-walkthrough-clean.mp4  the same picture with no captions

Captions are drawn with Pillow and overlaid, so any ffmpeg build works.
Run with the backend environment:  cd backend && uv run python ../tools/walkthrough/render.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
DELIVER = HERE.parents[1] / "deliverables"
STRIP = 56
WIDTH = 1440
ENCODE = ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"]


def main() -> None:
    DELIVER.mkdir(exist_ok=True)
    source = OUT / "walkthrough.webm"
    timeline = json.loads((OUT / "timeline.json").read_text())["timeline"]
    fonts = Path(importlib.util.find_spec("matplotlib").origin).parent / "mpl-data" / "fonts" / "ttf"
    font = ImageFont.truetype(str(fonts / "DejaVuSans.ttf"), 23)

    clean = DELIVER / "quoteline-walkthrough-clean.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), *ENCODE, str(clean)], check=True)

    inputs, chain = ["-i", str(source)], [f"[0:v]pad=iw:ih+{STRIP}:0:0:color=0x1C1B18[v0]"]
    for index, entry in enumerate(timeline):
        strip = Image.new("RGB", (WIDTH, STRIP), (28, 27, 24))
        draw = ImageDraw.Draw(strip)
        draw.text((WIDTH / 2, STRIP / 2), entry["scene"], font=font, fill=(255, 255, 255), anchor="mm")
        path = OUT / f"caption_{index:02d}.png"
        strip.save(path)
        end = timeline[index + 1]["seconds"] if index + 1 < len(timeline) else 100_000
        inputs += ["-i", str(path)]
        chain.append(
            f"[v{index}][{index + 1}:v]overlay=0:H-{STRIP}:enable='between(t,{entry['seconds']},{end})'[v{index + 1}]"
        )
    captioned = DELIVER / "quoteline-walkthrough.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(chain),
         "-map", f"[v{len(timeline)}]", *ENCODE, str(captioned)],
        check=True,
    )  # fmt: skip
    for path in (captioned, clean):
        print(f"{path.name}: {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
