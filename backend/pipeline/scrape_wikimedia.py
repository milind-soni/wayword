"""
Scrape sign photos from Wikimedia Commons categories.

Wikimedia Commons exposes a free MediaWiki API. Each image is CC-licensed (some
public domain, most CC-BY-SA). We pull from a curated list of categories per
language, download the original file, and write a sidecar JSON with the source
URL, license, and attribution so we can credit creators correctly later.

This script needs no API key. Be polite: include a real User-Agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx
from tqdm import tqdm

WIKIMEDIA_API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_USER_AGENT = (
    "WaywordSeedScraper/0.1 (https://github.com/milindsoni; contact: milindsoni201@gmail.com)"
)

# Curated category seeds. Wikimedia categories form a tree, so we recurse one
# level. These categories are deliberately broad — the Gemini tagging pass will
# discard anything that doesn't actually contain readable target-language text.
CATEGORY_SEEDS_BY_LANGUAGE: dict[str, list[str]] = {
    "de": [
        "Category:Signs in Germany",
        "Category:Street signs in Germany",
        "Category:Traffic signs of Germany",
        "Category:Shop signs in Germany",
        "Category:Information signs in Germany",
        "Category:Warning signs in Germany",
        "Category:Railway signs in Germany",
    ],
    "ja": [
        "Category:Signs in Japan",
        "Category:Street signs in Japan",
        "Category:Road signs in Japan",
        "Category:Shop signs in Japan",
        "Category:Railway station signs in Japan",
        "Category:Warning signs in Japan",
        "Category:Information signs in Japan",
    ],
}

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class ScrapedImage:
    page_title: str
    file_url: str
    descriptionurl: str
    width: int
    height: int
    license_short_name: str | None
    artist_html: str | None
    source_category: str


def fetch_category_members(
    http_client: httpx.Client,
    category_title: str,
    member_type: str,
    api_continue_token: dict[str, str] | None = None,
) -> tuple[list[dict], dict[str, str] | None]:
    """Fetch one page of category members. `member_type` is 'file' or 'subcat'."""

    request_params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category_title,
        "cmtype": member_type,
        "cmlimit": "500",
        "format": "json",
    }
    if api_continue_token:
        request_params.update(api_continue_token)

    response = http_client.get(WIKIMEDIA_API_ENDPOINT, params=request_params, timeout=30.0)
    response.raise_for_status()
    response_json = response.json()

    members = response_json.get("query", {}).get("categorymembers", [])
    next_continue_token = response_json.get("continue")
    return members, next_continue_token


def collect_file_titles_in_category_tree(
    http_client: httpx.Client,
    root_category_title: str,
    max_files: int,
    max_subcategories_to_recurse: int = 25,
) -> list[tuple[str, str]]:
    """Walk one level of subcategories, collecting (file_title, source_category)."""

    print(f"  walking category: {root_category_title}")
    collected_file_records: list[tuple[str, str]] = []

    # Files directly in the root category
    next_token: dict[str, str] | None = None
    while len(collected_file_records) < max_files:
        members, next_token = fetch_category_members(
            http_client, root_category_title, "file", next_token
        )
        for member in members:
            collected_file_records.append((member["title"], root_category_title))
            if len(collected_file_records) >= max_files:
                break
        if not next_token:
            break

    if len(collected_file_records) >= max_files:
        return collected_file_records

    # Subcategories — recurse one level
    sub_members, _ = fetch_category_members(http_client, root_category_title, "subcat")
    for subcategory_member in sub_members[:max_subcategories_to_recurse]:
        if len(collected_file_records) >= max_files:
            break
        subcategory_title = subcategory_member["title"]
        sub_token: dict[str, str] | None = None
        while len(collected_file_records) < max_files:
            files_in_sub, sub_token = fetch_category_members(
                http_client, subcategory_title, "file", sub_token
            )
            for sub_file in files_in_sub:
                collected_file_records.append((sub_file["title"], subcategory_title))
                if len(collected_file_records) >= max_files:
                    break
            if not sub_token:
                break

    return collected_file_records


def fetch_image_info_for_titles(
    http_client: httpx.Client, file_titles: Iterable[str]
) -> dict[str, dict]:
    """Batch lookup of imageinfo (URL, size, license) for up to 50 titles per call."""

    title_to_info: dict[str, dict] = {}
    title_list = list(file_titles)

    for batch_start in range(0, len(title_list), 50):
        batch_titles = title_list[batch_start : batch_start + 50]
        request_params = {
            "action": "query",
            "titles": "|".join(batch_titles),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "format": "json",
        }
        response = http_client.get(
            WIKIMEDIA_API_ENDPOINT, params=request_params, timeout=30.0
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            page_title = page.get("title")
            image_info_list = page.get("imageinfo")
            if page_title and image_info_list:
                title_to_info[page_title] = image_info_list[0]
        time.sleep(0.2)  # be polite

    return title_to_info


def build_scraped_image_record(
    file_title: str, image_info: dict, source_category: str
) -> ScrapedImage | None:
    file_url = image_info.get("url")
    if not file_url:
        return None
    extension = Path(file_url).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    extmetadata = image_info.get("extmetadata", {})
    license_short_name = extmetadata.get("LicenseShortName", {}).get("value")
    artist_html = extmetadata.get("Artist", {}).get("value")

    return ScrapedImage(
        page_title=file_title,
        file_url=file_url,
        descriptionurl=image_info.get("descriptionurl", ""),
        width=int(image_info.get("width", 0)),
        height=int(image_info.get("height", 0)),
        license_short_name=license_short_name,
        artist_html=artist_html,
        source_category=source_category,
    )


def stable_id_for_image(scraped_image: ScrapedImage) -> str:
    return hashlib.sha1(scraped_image.file_url.encode("utf-8")).hexdigest()[:16]


def download_image_to_disk(
    http_client: httpx.Client, scraped_image: ScrapedImage, output_directory: Path
) -> Path | None:
    output_directory.mkdir(parents=True, exist_ok=True)

    image_id = stable_id_for_image(scraped_image)
    extension = Path(scraped_image.file_url).suffix.lower()
    image_output_path = output_directory / f"{image_id}{extension}"
    metadata_output_path = output_directory / f"{image_id}.json"

    if image_output_path.exists() and metadata_output_path.exists():
        return image_output_path

    # Wikimedia's upload.wikimedia.org server is aggressive about rate limiting
    # bot-flagged user agents. Throttle downloads and retry once on 429.
    download_response = None
    for download_attempt_index in range(3):
        try:
            download_response = http_client.get(scraped_image.file_url, timeout=60.0)
            download_response.raise_for_status()
            break
        except httpx.HTTPStatusError as status_error:
            if status_error.response.status_code == 429 and download_attempt_index < 2:
                backoff_seconds = 5 * (download_attempt_index + 1)
                print(
                    f"  rate-limited on {image_id}, sleeping {backoff_seconds}s",
                    file=sys.stderr,
                )
                time.sleep(backoff_seconds)
                continue
            print(f"  skip {image_id}: {status_error}", file=sys.stderr)
            return None
        except httpx.HTTPError as download_error:
            print(f"  skip {image_id}: {download_error}", file=sys.stderr)
            return None

    if download_response is None:
        return None

    # Polite delay between successful downloads to stay under Wikimedia's bot threshold.
    time.sleep(0.6)

    image_output_path.write_bytes(download_response.content)
    metadata_output_path.write_text(
        json.dumps(
            {
                "id": image_id,
                "page_title": scraped_image.page_title,
                "file_url": scraped_image.file_url,
                "descriptionurl": scraped_image.descriptionurl,
                "width": scraped_image.width,
                "height": scraped_image.height,
                "license": scraped_image.license_short_name,
                "attribution_html": scraped_image.artist_html,
                "source_category": scraped_image.source_category,
                "source": "wikimedia_commons",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return image_output_path


def scrape_language(target_language_code: str, max_images: int, output_root: Path) -> int:
    if target_language_code not in CATEGORY_SEEDS_BY_LANGUAGE:
        raise SystemExit(f"unsupported language: {target_language_code}")

    output_directory_for_language = output_root / target_language_code
    seed_categories = CATEGORY_SEEDS_BY_LANGUAGE[target_language_code]
    images_per_seed_category = max(10, max_images // len(seed_categories) + 5)

    http_client = httpx.Client(headers={"User-Agent": WIKIMEDIA_USER_AGENT})

    print(f"[{target_language_code}] collecting file titles from {len(seed_categories)} categories")
    deduplicated_title_to_category: dict[str, str] = {}
    for seed_category_title in seed_categories:
        try:
            file_records = collect_file_titles_in_category_tree(
                http_client, seed_category_title, images_per_seed_category
            )
        except httpx.HTTPError as walk_error:
            print(f"  failed walking {seed_category_title}: {walk_error}", file=sys.stderr)
            continue
        for file_title, source_category in file_records:
            if file_title not in deduplicated_title_to_category:
                deduplicated_title_to_category[file_title] = source_category

    print(f"[{target_language_code}] {len(deduplicated_title_to_category)} unique candidate files")
    title_to_image_info = fetch_image_info_for_titles(
        http_client, deduplicated_title_to_category.keys()
    )

    download_count = 0
    for file_title, image_info in tqdm(
        title_to_image_info.items(), desc=f"download {target_language_code}"
    ):
        if download_count >= max_images:
            break
        scraped_image_record = build_scraped_image_record(
            file_title, image_info, deduplicated_title_to_category[file_title]
        )
        if scraped_image_record is None:
            continue
        if download_image_to_disk(http_client, scraped_image_record, output_directory_for_language):
            download_count += 1

    http_client.close()
    print(f"[{target_language_code}] downloaded {download_count} images to {output_directory_for_language}")
    return download_count


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Scrape sign photos from Wikimedia Commons")
    argument_parser.add_argument("--language", required=True, choices=["de", "ja"])
    argument_parser.add_argument("--limit", type=int, default=200)
    argument_parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "raw",
    )
    parsed_args = argument_parser.parse_args()
    scrape_language(parsed_args.language, parsed_args.limit, parsed_args.out)


if __name__ == "__main__":
    main()
