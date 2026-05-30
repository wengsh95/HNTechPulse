/* ================================================================
   Props Extractors — map Python elementProps to typed card props
   ================================================================ */

import type {
  CoverCardProps,
  EventCardProps,
  AtmosphereCardProps,
  ClosingCardProps,
  Highlight,
  CategoryBucket,
  AnalysisItem,
  Quote,
  StanceDistribution,
  CompletedStory,
  DigestStats,
  HeatLevel,
  ControversyLevel,
  Stance,
} from "./cardTypes";

// ---- generic helpers ----

function str(val: unknown, fallback = ""): string {
  if (val === undefined || val === null) return fallback;
  return typeof val === "string" ? val : String(val);
}

function num(val: unknown, fallback = 0): number {
  if (val === undefined || val === null) return fallback;
  if (typeof val === "number") return val;
  const n = Number(val);
  return Number.isFinite(n) ? n : fallback;
}

function arr<T>(val: unknown, fallback: T[] = []): T[] {
  return Array.isArray(val) ? (val as T[]) : fallback;
}

function obj(val: unknown): Record<string, unknown> {
  return val && typeof val === "object" && !Array.isArray(val)
    ? (val as Record<string, unknown>)
    : {};
}

// ---- CoverCard ----

export function extractCoverProps(
  elementProps: Record<string, unknown>,
): CoverCardProps {
  const headline = str(elementProps.headline, "HN每日观察");
  const dateLabel = str(elementProps.subtitle, "");

  // categories from section_counts
  const sectionCounts = obj(elementProps.section_counts);
  const categories: CategoryBucket[] = [];
  const focusCount = num(sectionCounts.focus);
  if (focusCount > 0) {
    categories.push({ label: "重点", count: focusCount, color: "red", flex: focusCount });
  }

  // highlights from highlight_entries
  const rawHighlights = arr<Record<string, unknown>>(
    elementProps.highlight_entries,
  );
  const highlights: Highlight[] = rawHighlights.slice(0, 3).map((h, i) => ({
    rank: i + 1,
    editorAngle: str(h.editor_angle, str(h.story_title, "")),
    hnScore: num(h.score),
    commentCount: num(h.comment_count),
    originalTitle: str(h.original_title, ""),
  }));

  return { headline, dateLabel, categories, highlights };
}

// ---- EventCard ----

const HEAT_ORDER: HeatLevel[] = ["L1", "L2", "L3"];

function toHeatLevel(val: string): HeatLevel {
  const upper = val.toUpperCase();
  if (upper === "L1" || upper === "L2" || upper === "L3") return upper as HeatLevel;
  // Chinese labels
  if (val === "今日最热" || val === "高热度") return "L3";
  if (val === "中等热度" || val === "较高热度") return "L2";
  // try numeric
  const n = Number(val);
  if (n >= 3) return "L3";
  if (n >= 2) return "L2";
  return "L1";
}

function extractAnalysis(keyPoints: unknown[]): AnalysisItem[] {
  if (!Array.isArray(keyPoints)) return [];
  return keyPoints
    .map((kp) => {
      if (!kp || typeof kp !== "object") return null;
      const o = kp as Record<string, unknown>;
      const label = str(o.label);
      const text = str(o.text);
      if (!label || !text) return null;
      const type =
        label === "为何关注" || label === "为什么关注" ? "why" : "impact";
      return { type, text };
    })
    .filter((a): a is AnalysisItem => a !== null)
    .slice(0, 2);
}

export function extractEventProps(
  elementProps: Record<string, unknown>,
): EventCardProps {
  const displayIndex = num(elementProps.display_index);
  const index = displayIndex + 1;
  const total = num(elementProps.story_count);
  const domain = str(elementProps.source_domain);
  const title =
    str(elementProps.editor_angle) ||
    str(elementProps.title_cn) ||
    str(elementProps.story_title);
  const sourceTitle = str(elementProps.source_title, title);
  const englishTitle =
    sourceTitle !== title ? sourceTitle : undefined;

  const heatLevelRaw = str(elementProps.heat_level, "L1");
  const heatLevel = toHeatLevel(heatLevelRaw);
  const heatLabel = heatLevelRaw;
  const category = str(elementProps.category);
  const hnScore = num(elementProps.score);
  const commentCount = num(elementProps.comment_count);
  const analysis = extractAnalysis(arr(elementProps.key_points));

  const keywords = arr<string>(
    elementProps.keywords,
  )
    .filter((k): k is string => typeof k === "string" && k.length > 0)
    .slice(0, 4);

  const imageType = str(elementProps.image_type);
  const imageSrc = str(elementProps.image_src);
  const isLogo = imageType === "logo";
  const imageUrl = !isLogo && imageSrc ? imageSrc : undefined;
  const logoUrl = isLogo && imageSrc ? imageSrc : undefined;

  return {
    index,
    total,
    domain,
    title,
    englishTitle,
    heatLevel,
    heatLabel,
    category,
    hnScore,
    commentCount,
    analysis,
    keywords,
    imageUrl,
    logoUrl,
  };
}

// ---- AtmosphereCard ----

function toControversyLevel(score: number): ControversyLevel {
  if (score <= 3) return "consensus";
  if (score <= 7) return "divided";
  return "highly_controversial";
}

function normalizeStance(val: unknown): Stance {
  const s = str(val).toLowerCase();
  if (s === "支持" || s === "support" || s === "supportive" || s === "positive")
    return "support";
  if (
    s === "质疑" ||
    s === "skeptic" ||
    s === "skeptical" ||
    s === "sceptical" ||
    s === "negative" ||
    s === "critical"
  )
    return "skeptic";
  if (s === "中立" || s === "neutral") return "neutral";
  if (s === "调侃" || s === "tease") return "tease";
  if (s === "担忧" || s === "worry") return "worry";
  return "neutral";
}

export function extractAtmosphereProps(
  elementProps: Record<string, unknown>,
): AtmosphereCardProps {
  const controversyScore = num(elementProps.controversy_score);
  const controversyLevel = toControversyLevel(controversyScore);

  const debateTopics = arr<string>(elementProps.debate_focus)
    .filter((d): d is string => typeof d === "string" && d.length > 0)
    .slice(0, 3);

  // stance_distribution
  const rawDist = obj(elementProps.stance_distribution);
  const stanceDistribution: StanceDistribution = {
    support: num(rawDist.support) || num(rawDist["支持"]) || num(rawDist.supportive) || 0,
    skeptic:
      num(rawDist.skeptic) ||
      num(rawDist["质疑"]) ||
      num(rawDist.skeptical) ||
      num(rawDist.sceptical) ||
      0,
    neutral: num(rawDist.neutral) || num(rawDist["中立"]) || 0,
    tease: num(rawDist.tease) || num(rawDist["调侃"]) || 0,
    worry: num(rawDist.worry) || num(rawDist["担忧"]) || 0,
  };

  const totalComments = num(elementProps.comment_count);

  // quotes
  const rawQuotes = arr<Record<string, unknown>>(elementProps.quotes);
  const quotes: Quote[] = rawQuotes.slice(0, 3).map((q) => ({
    text: str(q.display_text, str(q.text, "")),
    author: str(q.author, ""),
    likes: num(q.upvotes, num(q.likes)),
    stance: normalizeStance(q.stance),
  }));

  return {
    controversyScore,
    controversyLevel,
    debateTopics,
    stanceDistribution,
    totalComments,
    quotes,
    displayIndex: num(elementProps.display_index),
    storyCount: num(elementProps.story_count),
  };
}

// ---- ClosingCard ----

export function extractClosingProps(
  elementProps: Record<string, unknown>,
): ClosingCardProps {
  const signalLabel = str(elementProps.signal_label, "今日信号");
  const summary = str(elementProps.signal) || str(elementProps.question) || "";

  const keywords = arr<string>(elementProps.keywords)
    .filter((k): k is string => typeof k === "string" && k.length > 0)
    .slice(0, 5);

  const rawItems = arr<Record<string, unknown>>(elementProps.summary_items);
  const completedStories: CompletedStory[] = rawItems
    .filter((item) => item && item.title)
    .slice(0, 3)
    .map((item) => ({
      category: str(item.category, ""),
      title: str(item.title, ""),
    }));

  const totals = obj(elementProps.totals);
  const progressTotal = num(totals.story_count, completedStories.length);
  const progressDone = progressTotal; // assume all done for closing

  const stats: DigestStats = {
    storyCount: num(totals.story_count),
    points: num(totals.score_total),
    comments: num(totals.comment_total),
  };

  const vibe = str(elementProps.visual_mood, "");

  // Compute pie percentages from stance distribution if available
  const rawDist = obj(elementProps.stance_distribution);
  const totalStance =
    num(rawDist.support) +
    num(rawDist.skeptic) +
    num(rawDist.neutral) +
    num(rawDist.tease) +
    num(rawDist.worry);
  const focusPct = totalStance > 0 ? 62 : 0; // default
  const atmospherePct = totalStance > 0 ? 38 : 0;

  return {
    signalLabel,
    summary,
    keywords,
    progressDone,
    progressTotal,
    focusPct,
    atmospherePct,
    completedStories,
    stats,
    vibe,
  };
}
