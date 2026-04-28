"""
Tag scraped sign images with Gemini 2.5 Flash.

For each image in data/raw/<lang>/, this calls Gemini with a structured prompt
that asks for: detected text regions with normalized bounding boxes, translation,
romanization (Japanese only), per-region grammar breakdown, an overall category,
a CEFR-style difficulty band, and a short "where you'd see it" note.

Output is one JSON file per image in data/tagged/<lang>/<id>.json. Images that
contain no readable target-language text are written with `"usable": false` so
the feed can skip them without re-running the model.

Bounding boxes follow Gemini's native convention: integers 0-1000 normalized
[ymin, xmin, ymax, xmax]. The frontend converts to percentages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from PIL import Image
from tqdm import tqdm

GEMINI_MODEL_NAME = "gemini-2.5-flash"

LANGUAGE_NAME_BY_CODE = {"de": "German", "ja": "Japanese"}

PROMPT_TEMPLATE = """\
You are analyzing a photograph of a real-world sign, label, menu, or notice.
The expected language on the sign is {language_name}.

Return a single JSON object (no prose, no markdown fences) with this schema:

{{
  "usable": boolean,                  // false if image has no readable {language_name} text
  "reject_reason": string | null,     // why if not usable (e.g. "no text", "wrong language")
  "language_detected": string,        // ISO 639-1 of dominant text language
  "regions": [
    {{
      "original": string,              // the exact text shown
      "translation": string,           // natural English translation
      "romanization": string | null,   // pronunciation guide; for Japanese give romaji, for German give null
      "bbox": [ymin, xmin, ymax, xmax],// integers 0-1000, normalized to image
      "breakdown": string              // brief explanation of words/grammar/kanji
    }}
  ],
  "category": string,                 // one of: transit, traffic, food, shop, warning, info, bureaucratic, graffiti, other
  "difficulty": string,               // one of: A1, A2, B1, B2, C1
  "where_youd_see_it": string,        // one short sentence, end-user friendly
  "cultural_note": string | null      // optional: anything a learner would find interesting
}}

If multiple text regions overlap, return the most prominent one. If a region's
text is partially cut off or illegible, omit that region. Be strict about
`usable`: only return true when there is clear, readable {language_name} text.
"""


def build_gemini_client_from_env() -> genai.Client:
    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not gemini_api_key:
        raise SystemExit(
            "GEMINI_API_KEY not set. Copy backend/.env.example to backend/.env and add your key."
        )
    return genai.Client(api_key=gemini_api_key)


def list_image_paths_in_directory(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def parse_model_json_response(raw_response_text: str) -> dict | None:
    """Strip ```json fences if present, then json.loads."""
    cleaned_text = raw_response_text.strip()
    if cleaned_text.startswith("```"):
        cleaned_text = cleaned_text.strip("`")
        if cleaned_text.lower().startswith("json"):
            cleaned_text = cleaned_text[4:]
        cleaned_text = cleaned_text.strip()
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        return None


def tag_single_image_with_gemini(
    gemini_client: genai.Client, image_path: Path, target_language_code: str
) -> dict | None:
    language_name = LANGUAGE_NAME_BY_CODE[target_language_code]
    prompt_text = PROMPT_TEMPLATE.format(language_name=language_name)

    pil_image = Image.open(image_path)
    if pil_image.mode not in {"RGB", "RGBA"}:
        pil_image = pil_image.convert("RGB")

    # Wikimedia originals are often 4-12 MB; Gemini does not need that resolution
    # to read most signs, and the upload latency dominates wall time. Resize to a
    # 1280px longest edge — OCR quality stays high, per-image time drops ~3x.
    longest_edge_pixels = max(pil_image.width, pil_image.height)
    max_longest_edge_pixels = 1280
    if longest_edge_pixels > max_longest_edge_pixels:
        resize_ratio = max_longest_edge_pixels / longest_edge_pixels
        resized_width = int(pil_image.width * resize_ratio)
        resized_height = int(pil_image.height * resize_ratio)
        pil_image = pil_image.resize((resized_width, resized_height), Image.LANCZOS)

    for attempt_index in range(3):
        try:
            generation_response = gemini_client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=[prompt_text, pil_image],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
        except Exception as gemini_error:
            print(f"  attempt {attempt_index + 1} error: {gemini_error}", file=sys.stderr)
            time.sleep(2 * (attempt_index + 1))
            continue

        response_text = getattr(generation_response, "text", None) or ""
        parsed_json = parse_model_json_response(response_text)
        if parsed_json is not None:
            return parsed_json

    return None


def tag_language_directory(target_language_code: str, data_root: Path, max_images: int | None) -> None:
    raw_directory = data_root / "raw" / target_language_code
    tagged_directory = data_root / "tagged" / target_language_code
    tagged_directory.mkdir(parents=True, exist_ok=True)

    if not raw_directory.exists():
        raise SystemExit(f"no raw directory at {raw_directory}; run scraper first")

    gemini_client = build_gemini_client_from_env()
    image_paths = list_image_paths_in_directory(raw_directory)
    if max_images is not None:
        image_paths = image_paths[:max_images]

    for image_path in tqdm(image_paths, desc=f"tag {target_language_code}"):
        tagged_output_path = tagged_directory / f"{image_path.stem}.json"
        if tagged_output_path.exists():
            continue

        tagging_result = tag_single_image_with_gemini(
            gemini_client, image_path, target_language_code
        )
        if tagging_result is None:
            tagging_result = {
                "usable": False,
                "reject_reason": "model_returned_no_json",
                "regions": [],
            }
        tagging_result["image_id"] = image_path.stem
        tagging_result["language"] = target_language_code

        tagged_output_path.write_text(json.dumps(tagging_result, ensure_ascii=False, indent=2))


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Tag scraped sign images with Gemini")
    argument_parser.add_argument("--language", required=True, choices=["de", "ja"])
    argument_parser.add_argument("--limit", type=int, default=None, help="Cap number of images")
    argument_parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    parsed_args = argument_parser.parse_args()
    tag_language_directory(parsed_args.language, parsed_args.data_root, parsed_args.limit)


if __name__ == "__main__":
    main()
