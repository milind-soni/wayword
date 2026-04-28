"use client";

import { useState } from "react";
import type { SignFeedCard, SignTextRegion } from "../lib/api";

interface SignCardProps {
  feedCard: SignFeedCard;
}

function bboxToPercentStyle(bbox: [number, number, number, number]) {
  const [ymin, xmin, ymax, xmax] = bbox;
  return {
    top: `${(ymin / 1000) * 100}%`,
    left: `${(xmin / 1000) * 100}%`,
    width: `${((xmax - xmin) / 1000) * 100}%`,
    height: `${((ymax - ymin) / 1000) * 100}%`,
  };
}

export function SignCard({ feedCard }: SignCardProps) {
  const [hasRevealedTranslation, setHasRevealedTranslation] = useState(false);
  const [activeRegionIndex, setActiveRegionIndex] = useState<number | null>(null);

  const activeRegion: SignTextRegion | null =
    activeRegionIndex !== null ? feedCard.regions[activeRegionIndex] ?? null : null;

  return (
    <section
      className="relative h-[100svh] w-full snap-start overflow-hidden bg-black"
      onClick={() => setHasRevealedTranslation((wasRevealed) => !wasRevealed)}
    >
      {/* Background image, full bleed */}
      <img
        src={feedCard.image_url}
        alt=""
        className="absolute inset-0 h-full w-full object-contain"
        draggable={false}
      />

      {/* Dim overlay only when revealed, to make text readable */}
      <div
        className={`pointer-events-none absolute inset-0 transition-opacity duration-300 ${
          hasRevealedTranslation ? "bg-black/55 opacity-100" : "opacity-0"
        }`}
      />

      {/* Bounding boxes — only shown when revealed */}
      {hasRevealedTranslation &&
        feedCard.regions.map((region, regionIndex) => (
          <button
            key={regionIndex}
            type="button"
            onClick={(clickEvent) => {
              clickEvent.stopPropagation();
              setActiveRegionIndex((previousIndex) =>
                previousIndex === regionIndex ? null : regionIndex,
              );
            }}
            className={`absolute rounded-md border-2 transition-colors ${
              activeRegionIndex === regionIndex
                ? "border-amber-300 bg-amber-300/20"
                : "border-white/80 bg-white/10 hover:bg-white/20"
            }`}
            style={bboxToPercentStyle(region.bbox)}
            aria-label={`Region: ${region.original}`}
          />
        ))}

      {/* Top-left meta chip */}
      <div className="absolute left-4 top-4 flex items-center gap-2 text-xs">
        <span className="rounded-full bg-white/15 px-2.5 py-1 font-medium uppercase tracking-wide backdrop-blur">
          {feedCard.language}
        </span>
        {feedCard.difficulty && (
          <span className="rounded-full bg-white/15 px-2.5 py-1 font-medium tracking-wide backdrop-blur">
            {feedCard.difficulty}
          </span>
        )}
        {feedCard.category && (
          <span className="rounded-full bg-white/15 px-2.5 py-1 capitalize backdrop-blur">
            {feedCard.category}
          </span>
        )}
      </div>

      {/* Tap hint when not yet revealed */}
      {!hasRevealedTranslation && (
        <div className="absolute inset-x-0 bottom-28 flex justify-center">
          <span className="rounded-full bg-white/15 px-4 py-2 text-sm backdrop-blur">
            tap to reveal
          </span>
        </div>
      )}

      {/* Bottom info panel */}
      {hasRevealedTranslation && (
        <div
          className="absolute inset-x-0 bottom-0 max-h-[55%] overflow-y-auto bg-gradient-to-t from-black/95 via-black/80 to-transparent px-5 pb-8 pt-10"
          onClick={(clickEvent) => clickEvent.stopPropagation()}
        >
          {activeRegion ? (
            <RegionDetailPanel region={activeRegion} />
          ) : (
            <FeedCardSummaryPanel feedCard={feedCard} />
          )}
        </div>
      )}
    </section>
  );
}

function FeedCardSummaryPanel({ feedCard }: { feedCard: SignFeedCard }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-x-3 gap-y-2 text-2xl font-semibold leading-tight">
        {feedCard.regions.map((region, regionIndex) => (
          <span key={regionIndex}>
            {region.original}
            <span className="ml-2 text-base font-normal text-white/60">
              {region.translation}
            </span>
          </span>
        ))}
      </div>
      {feedCard.where_youd_see_it && (
        <p className="text-sm text-white/70">{feedCard.where_youd_see_it}</p>
      )}
      {feedCard.cultural_note && (
        <p className="text-sm italic text-amber-200/80">{feedCard.cultural_note}</p>
      )}
      <p className="pt-2 text-xs text-white/40">tap a highlighted region for details</p>
    </div>
  );
}

function RegionDetailPanel({ region }: { region: SignTextRegion }) {
  return (
    <div className="space-y-2">
      <div className="text-3xl font-semibold leading-tight">{region.original}</div>
      {region.romanization && (
        <div className="text-sm uppercase tracking-wide text-white/50">
          {region.romanization}
        </div>
      )}
      <div className="text-lg text-white/90">{region.translation}</div>
      {region.breakdown && (
        <p className="pt-1 text-sm text-white/70">{region.breakdown}</p>
      )}
    </div>
  );
}
