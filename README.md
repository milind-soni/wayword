# Wayword

A TikTok-style language learning feed built around real-world signs.

Currently scoped to **German** and **Japanese**. The feed serves scraped, CC-licensed images of signs/labels/menus. Each image is processed once at ingest by a vision-language model that returns the original text, translation, normalized bounding boxes, and difficulty/category metadata. The frontend is a vertical-scroll feed with tap-to-reveal overlays.

## Status

Working name. MVP in progress.

## Layout

```
wayword/
├── backend/
│   ├── pipeline/        scrapers + Gemini tagging
│   ├── app/             FastAPI service
│   └── data/            local cache of scraped + tagged data (gitignored)
└── frontend/            Next.js feed
```

## Local setup

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Scrape ~200 images per language from Wikimedia Commons (no API key needed)
python -m pipeline.scrape_wikimedia --language de --limit 200
python -m pipeline.scrape_wikimedia --language ja --limit 200

# Tag with Gemini (requires GEMINI_API_KEY in .env)
python -m pipeline.tag_with_gemini --language de
python -m pipeline.tag_with_gemini --language ja
```
