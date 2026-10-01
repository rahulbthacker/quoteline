"""Stitch narration clips onto the walkthrough video.

Input:  deliverables/quoteline-walkthrough.mp4  (silent, with caption strip)
        deliverables/voice/clip_<key>.mp3       (one narration clip per scene)
Output: deliverables/quoteline-walkthrough-voiced.mp4

Each clip is anchored to a moment in its scene (SCENES). Scenes with more picture than
narration are played slightly faster, up to MAX_SPEED, so there is no long dead air; the two
long waits for live model calls are played at WAIT_SPEED with a label saying so. The last
frame is held so the closing line can finish.

Run with the backend environment:  cd backend && uv run python ../tools/walkthrough/voice.py
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DELIVER = ROOT / "deliverables"
SOURCE = DELIVER / "quoteline-walkthrough.mp4"
OUTPUT = DELIVER / "quoteline-walkthrough-voiced.mp4"
VIDEO_LENGTH = 568.08
WAIT_SPEED = 6  # the two long waits for live model calls
MAX_SPEED = 1.35  # other scenes are tightened no more than this
TRAIL = 2.0  # seconds of picture left after a narration clip ends
TAIL_HOLD = 4.0

# (scene start on the silent video, kind, clips as (key, seconds into the scene))
SCENES = [
    (0.0, "scene", [("01", 2.5)]),
    (44.0, "scene", [("02", 0.5)]),
    (58.0, "scene", [("03", 0.8)]),
    (71.0, "scene", [("04", 1.0)]),
    (97.0, "scene", [("05", 1.0)]),
    (128.0, "scene", [("06", 1.0)]),
    (162.0, "scene", [("07", 1.0)]),
    (189.0, "scene", [("08", 1.0)]),
    (208.0, "scene", [("09", 0.8)]),
    (219.0, "scene", [("10", 4.0)]),
    (250.0, "scene", [("11", 1.0)]),
    (282.0, "wait", []),  # the analyst is working
    (312.0, "scene", [("12", 3.0)]),
    (359.0, "scene", [("13", 3.0)]),
    (383.0, "scene", [("14", 5.0)]),
    (433.0, "scene", [("15", 1.0)]),
    (454.0, "scene", [("16", 1.0)]),
    (479.0, "scene", [("17a", 1.0)]),
    (507.0, "wait", []),  # the co-pilot is working
    (544.0, "fixed", [("17b", 4.5), ("17c", 15.0), ("18", 24.0)]),
]


def clip_seconds(key: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(DELIVER / "voice" / f"clip_{key}.mp3")],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return float(out.stdout.strip())


def plan() -> tuple[list[dict], dict[str, float], float]:
    """Per scene: how fast to play it, and where each clip lands on the output clock."""
    segments, starts, clock = [], {}, 0.0
    for index, (start, kind, clips) in enumerate(SCENES):
        end = SCENES[index + 1][0] if index + 1 < len(SCENES) else VIDEO_LENGTH
        length = end - start
        if kind == "wait":
            speed = WAIT_SPEED
        elif kind == "fixed":
            speed = 1.0
        else:
            key, offset = clips[0]
            needed = offset + clip_seconds(key) + TRAIL
            speed = max(1.0, min(MAX_SPEED, length / needed))
        for key, offset in clips:
            starts[key] = clock + offset / speed
        segments.append({"start": start, "end": end, "speed": speed, "at": clock, "wait": kind == "wait"})
        clock += length / speed
    return segments, starts, clock + TAIL_HOLD


def label_png() -> Path:
    fonts = Path(importlib.util.find_spec("matplotlib").origin).parent / "mpl-data" / "fonts" / "ttf"
    font = ImageFont.truetype(str(fonts / "DejaVuSans.ttf"), 22)
    text = f"Live model call, shown at {WAIT_SPEED}x speed"
    width = int(font.getlength(text)) + 44
    image = Image.new("RGBA", (width, 46), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, width - 1, 45], radius=23, fill=(191, 74, 31, 240))
    draw.text((width / 2, 23), text, font=font, fill=(255, 255, 255, 255), anchor="mm")
    path = DELIVER / "voice" / "label.png"
    image.save(path)
    return path


def main() -> None:
    segments, starts, total = plan()
    graph = []
    for index, seg in enumerate(segments):
        hold = f",tpad=stop_mode=clone:stop_duration={TAIL_HOLD}" if index == len(segments) - 1 else ""
        graph.append(
            f"[0:v]trim={seg['start']}:{seg['end']},setpts=(PTS-STARTPTS)/{seg['speed']:.4f},fps=25{hold}[v{index}]"
        )
    names = "".join(f"[v{i}]" for i in range(len(segments)))
    waits = [seg for seg in segments if seg["wait"]]
    enable = "+".join(
        f"between(t,{seg['at']:.2f},{seg['at'] + (seg['end'] - seg['start']) / seg['speed']:.2f})" for seg in waits
    )
    graph += [
        f"{names}concat=n={len(segments)}:v=1:a=0[joined]",
        f"[joined][1:v]overlay=(W-w)/2:70:enable='{enable}'[video]",
    ]

    inputs = ["-i", str(SOURCE), "-i", str(label_png())]
    mixed = []
    for index, (key, start) in enumerate(starts.items()):
        inputs += ["-i", str(DELIVER / "voice" / f"clip_{key}.mp3")]
        graph.append(f"[{index + 2}:a]aresample=48000,adelay={int(start * 1000)}:all=1[a{index}]")
        mixed.append(f"[a{index}]")
    graph.append(
        f"{''.join(mixed)}amix=inputs={len(mixed)}:normalize=0:dropout_transition=0,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11,apad,atrim=0:{total:.2f}[audio]"
    )
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(graph),
         "-map", "[video]", "-map", "[audio]", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(OUTPUT)],
        check=True,
    )  # fmt: skip
    print(f"{OUTPUT.name}: {OUTPUT.stat().st_size / 1e6:.1f} MB, {int(total // 60)} min {total % 60:.0f} s")
    for seg in segments:
        print(f"  scene from {seg['start']:>5.0f}s plays at {seg['speed']:.2f}x, lands at {int(seg['at'] // 60)}:{seg['at'] % 60:04.1f}")


if __name__ == "__main__":
    main()
