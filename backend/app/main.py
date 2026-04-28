"""
Wayword API.

For the MVP this is a thin file-backed read API: it reads tagged sign JSON from
data/tagged/<lang>/ and serves the original images from data/raw/<lang>/. No DB.
Once we need server-side accounts or shared SRS we'll move into Postgres.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DATA_ROOT_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
RAW_IMAGES_DIRECTORY = DATA_ROOT_DIRECTORY / "raw"
TAGGED_JSON_DIRECTORY = DATA_ROOT_DIRECTORY / "tagged"

SupportedLanguage = Literal["de", "ja"]


class SignTextRegion(BaseModel):
    original: str
    translation: str
    romanization: str | None = None
    bbox: list[int]  # [ymin, xmin, ymax, xmax] normalized to 0-1000
    breakdown: str


class SignFeedCard(BaseModel):
    id: str
    language: str
    image_url: str
    regions: list[SignTextRegion]
    category: str | None = None
    difficulty: str | None = None
    where_youd_see_it: str | None = None
    cultural_note: str | None = None
    attribution_html: str | None = None
    source_url: str | None = None


fastapi_app = FastAPI(title="Wayword API", version="0.1.0")

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if RAW_IMAGES_DIRECTORY.exists():
    fastapi_app.mount(
        "/images", StaticFiles(directory=RAW_IMAGES_DIRECTORY), name="images"
    )


def load_raw_image_metadata(language_code: str, image_id: str) -> dict | None:
    metadata_path = RAW_IMAGES_DIRECTORY / language_code / f"{image_id}.json"
    if not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text())


def load_tagged_card_for_image(language_code: str, image_id: str) -> SignFeedCard | None:
    tagged_path = TAGGED_JSON_DIRECTORY / language_code / f"{image_id}.json"
    if not tagged_path.exists():
        return None

    tagged_record = json.loads(tagged_path.read_text())
    if not tagged_record.get("usable"):
        return None

    raw_metadata = load_raw_image_metadata(language_code, image_id) or {}
    image_extension_candidates = [".jpg", ".jpeg", ".png", ".webp"]
    image_url_path: str | None = None
    for extension in image_extension_candidates:
        if (RAW_IMAGES_DIRECTORY / language_code / f"{image_id}{extension}").exists():
            image_url_path = f"/images/{language_code}/{image_id}{extension}"
            break
    if image_url_path is None:
        return None

    region_models: list[SignTextRegion] = []
    for region_record in tagged_record.get("regions", []):
        bbox_value = region_record.get("bbox") or [0, 0, 1000, 1000]
        if not (isinstance(bbox_value, list) and len(bbox_value) == 4):
            bbox_value = [0, 0, 1000, 1000]
        region_models.append(
            SignTextRegion(
                original=region_record.get("original", ""),
                translation=region_record.get("translation", ""),
                romanization=region_record.get("romanization"),
                bbox=[int(bbox_coordinate) for bbox_coordinate in bbox_value],
                breakdown=region_record.get("breakdown", ""),
            )
        )

    if not region_models:
        return None

    return SignFeedCard(
        id=image_id,
        language=language_code,
        image_url=image_url_path,
        regions=region_models,
        category=tagged_record.get("category"),
        difficulty=tagged_record.get("difficulty"),
        where_youd_see_it=tagged_record.get("where_youd_see_it"),
        cultural_note=tagged_record.get("cultural_note"),
        attribution_html=raw_metadata.get("attribution_html"),
        source_url=raw_metadata.get("descriptionurl"),
    )


def list_all_usable_cards_for_language(language_code: str) -> list[SignFeedCard]:
    tagged_directory_for_language = TAGGED_JSON_DIRECTORY / language_code
    if not tagged_directory_for_language.exists():
        return []

    usable_cards: list[SignFeedCard] = []
    for tagged_file in tagged_directory_for_language.iterdir():
        if tagged_file.suffix != ".json":
            continue
        card_or_none = load_tagged_card_for_image(language_code, tagged_file.stem)
        if card_or_none is not None:
            usable_cards.append(card_or_none)
    return usable_cards


@fastapi_app.get("/health")
def get_health_status() -> dict:
    return {"status": "ok"}


@fastapi_app.get("/feed", response_model=list[SignFeedCard])
def get_feed_cards(
    language: SupportedLanguage = Query(..., description="ISO code: de or ja"),
    limit: int = Query(20, ge=1, le=100),
    seed: int | None = Query(
        None,
        description="Optional integer to make ordering reproducible across pulls",
    ),
) -> list[SignFeedCard]:
    all_cards = list_all_usable_cards_for_language(language)
    if not all_cards:
        raise HTTPException(
            status_code=404,
            detail=f"no tagged cards for language={language}; run scraper + tagger",
        )

    random_generator = random.Random(seed) if seed is not None else random.Random()
    random_generator.shuffle(all_cards)
    return all_cards[:limit]


@fastapi_app.get("/sign/{language}/{image_id}", response_model=SignFeedCard)
def get_single_sign_card(language: SupportedLanguage, image_id: str) -> SignFeedCard:
    card_or_none = load_tagged_card_for_image(language, image_id)
    if card_or_none is None:
        raise HTTPException(status_code=404, detail="sign not found or not usable")
    return card_or_none
