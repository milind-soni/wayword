"use client";

import { useEffect, useState } from "react";
import { SignCard } from "./components/SignCard";
import { fetchFeedCards, type SignFeedCard, type SupportedLanguage } from "./lib/api";

export default function FeedPage() {
  const [selectedLanguage, setSelectedLanguage] = useState<SupportedLanguage>("ja");
  const [feedCards, setFeedCards] = useState<SignFeedCard[]>([]);
  const [loadingError, setLoadingError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    setFeedCards([]);
    setLoadingError(null);
    fetchFeedCards(selectedLanguage, 30)
      .then((cards) => {
        if (!isCancelled) setFeedCards(cards);
      })
      .catch((fetchError: Error) => {
        if (!isCancelled) setLoadingError(fetchError.message);
      });
    return () => {
      isCancelled = true;
    };
  }, [selectedLanguage]);

  return (
    <main className="relative h-[100svh] w-full overflow-hidden bg-black">
      {/* Language switcher pinned top-right */}
      <div className="pointer-events-none absolute right-3 top-3 z-20 flex gap-2">
        {(["ja", "de"] as const).map((languageCode) => (
          <button
            key={languageCode}
            type="button"
            onClick={() => setSelectedLanguage(languageCode)}
            className={`pointer-events-auto rounded-full px-3 py-1 text-xs font-medium uppercase tracking-wide backdrop-blur transition-colors ${
              selectedLanguage === languageCode
                ? "bg-white text-black"
                : "bg-white/15 text-white hover:bg-white/25"
            }`}
          >
            {languageCode}
          </button>
        ))}
      </div>

      {loadingError && (
        <div className="flex h-full items-center justify-center px-6 text-center text-sm text-white/60">
          <div>
            <p className="text-lg">Couldn't load feed.</p>
            <p className="mt-2 text-white/40">{loadingError}</p>
            <p className="mt-2 text-white/40">
              Make sure the backend is running on :8000 and you've tagged some images.
            </p>
          </div>
        </div>
      )}

      {!loadingError && feedCards.length === 0 && (
        <div className="flex h-full items-center justify-center text-sm text-white/40">
          loading…
        </div>
      )}

      <div className="h-full w-full snap-y snap-mandatory overflow-y-scroll">
        {feedCards.map((feedCard) => (
          <SignCard key={feedCard.id} feedCard={feedCard} />
        ))}
      </div>
    </main>
  );
}
