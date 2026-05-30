/* ================================================================
   Shared Card Prop Types — warm paper theme
   ================================================================ */

// ---- heat levels ----
export type HeatLevel = "L1" | "L2" | "L3";

// ---- controversy labels ----
export type ControversyLevel = "consensus" | "divided" | "highly_controversial";

// ---- stance types ----
export type Stance = "support" | "skeptic" | "neutral" | "tease" | "worry";

// ---- category color tiers ----
export type TierColor = "red" | "amber" | "dim";

// ---- analysis type ----
export type AnalysisType = "why" | "impact";

// ================================================================
// CoverCard
// ================================================================
export interface Highlight {
  rank: number;
  editorAngle: string;
  hnScore: number;
  commentCount: number;
  originalTitle: string;
}

export interface CategoryBucket {
  label: string;
  count: number;
  color: TierColor;
  flex: number;
}

export interface CoverCardProps {
  headline: string;
  dateLabel: string;
  categories: CategoryBucket[];
  highlights: Highlight[];
}

// ================================================================
// EventCard
// ================================================================
export interface AnalysisItem {
  type: AnalysisType;
  text: string;
}

export interface EventCardProps {
  index: number;
  total: number;
  domain: string;
  title: string;
  englishTitle?: string;
  heatLevel: HeatLevel;
  heatLabel: string;
  category: string;
  hnScore: number;
  commentCount: number;
  analysis: AnalysisItem[];
  keywords: string[];
  imageUrl?: string;
  logoUrl?: string;
}

// ================================================================
// AtmosphereCard
// ================================================================
export interface Quote {
  text: string;
  author: string;
  likes: number;
  stance: Stance;
}

export interface StanceDistribution {
  support: number;
  skeptic: number;
  neutral: number;
  tease: number;
  worry: number;
}

export interface AtmosphereCardProps {
  controversyScore: number;
  controversyLevel: ControversyLevel;
  debateTopics: string[];
  stanceDistribution: StanceDistribution;
  totalComments: number;
  quotes: Quote[];
}

// ================================================================
// ClosingCard
// ================================================================
export interface CompletedStory {
  category: string;
  title: string;
}

export interface DigestStats {
  storyCount: number;
  points: number;
  comments: number;
}

export interface ClosingCardProps {
  signalLabel: string;
  summary: string;
  keywords: string[];
  progressDone: number;
  progressTotal: number;
  focusPct: number;
  atmospherePct: number;
  completedStories: CompletedStory[];
  stats: DigestStats;
  vibe: string;
}
