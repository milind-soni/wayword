export type SupportedLanguage = "de" | "ja";

export interface SignTextRegion {
  original: string;
  translation: string;
  romanization: string | null;
  bbox: [number, number, number, number]; // [ymin, xmin, ymax, xmax] in 0-1000
  breakdown: string;
}

export interface SignFeedCard {
  id: string;
  language: string;
  image_url: string;
  regions: SignTextRegion[];
  category: string | null;
  difficulty: string | null;
  where_youd_see_it: string | null;
  cultural_note: string | null;
  attribution_html: string | null;
  source_url: string | null;
}

export async function fetchFeedCards(
  language: SupportedLanguage,
  limit: number = 20,
): Promise<SignFeedCard[]> {
  const apiUrl = `/api/feed?language=${language}&limit=${limit}`;
  const response = await fetch(apiUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`feed fetch failed: ${response.status}`);
  }
  return (await response.json()) as SignFeedCard[];
}
