"""Generate a synthetic Korean course line and measure local OCR extraction."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".ocrdeps"))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

image = Image.new("RGB", (1500, 260), "white")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 48)
draw.text((45, 45), "CDA0143 고급자료구조 3학점", fill="black", font=font)
path = ROOT / "logs/ocr_sample.png"
image.save(path)

import easyocr  # noqa: E402

started = time.monotonic()
reader = easyocr.Reader(["ko", "en"], gpu=False, model_storage_directory=str(ROOT / ".ocrmodels"))
print("reader_seconds", round(time.monotonic() - started, 2), flush=True)
started = time.monotonic()
print("ocr", reader.readtext(str(path), detail=1), flush=True)
print("ocr_seconds", round(time.monotonic() - started, 2), flush=True)
