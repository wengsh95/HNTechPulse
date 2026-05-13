/** Shared props for Remotion scene elements. */
export interface ElementProps {
  elementProps: Record<string, unknown>;
  duration: number;
  width: number;
  height: number;
}

/** Safely read a value from element props with runtime type validation. */
export function p<T = string>(props: Record<string, unknown>, key: string, fallback: T): T {
  const val = props[key];
  if (val === undefined || val === null) return fallback;
  if (typeof fallback === "number") return (typeof val === "number" ? val : Number(val) || fallback) as T;
  if (typeof fallback === "string") return (typeof val === "string" ? val : String(val)) as T;
  if (typeof fallback === "boolean") return (typeof val === "boolean" ? val : Boolean(val)) as T;
  return val as T;
}

const ENTITY_MAP: Record<string, string> = {
  "&quot;": '"',
  "&#34;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&gt;": ">",
  "&lt;": "<",
  "&amp;": "&",
  "&nbsp;": " ",
};

export const UI_TEXT = {
  topStories: "今日热点",
  top10: "热榜前十",
  title: "标题",
  heat: "热度",
  comments: "评论",
  keyVoices: "代表观点",
  original: "原文",
  discussionMood: "讨论气氛",
  eventDetail: "事件详情",
  keywords: "关键词",
  debateFocus: "争议焦点",
  controversy: "争议指数",
  scoreSuffix: "/ 10",
  whyItMatters: "为何关注",
};

const STANCE_LABELS: Record<string, string> = {
  supportive: "支持",
  support: "支持",
  positive: "支持",
  skeptical: "质疑",
  sceptical: "质疑",
  negative: "质疑",
  critical: "质疑",
  neutral: "中立",
  mixed: "分歧",
  informative: "补充",
  clarification: "补充",
  question: "追问",
};

export function stripHtml(text: string): string {
  if (!text) return "";
  return String(text).replace(/<[^>]+>/g, "");
}

export function decodeHtmlEntities(text: string): string {
  if (!text) return "";
  return String(text).replace(/&(quot|#34|#x27|#39|gt|lt|amp|nbsp);/g, (entity) => ENTITY_MAP[entity] ?? entity);
}

export function cleanText(text: string): string {
  if (!text) return "";
  return decodeHtmlEntities(stripHtml(String(text)))
    .replace(/\s+/g, " ")
    .trim();
}

export function truncate(text: string, maxLen: number): string {
  const cleaned = cleanText(text);
  if (!cleaned || maxLen <= 0) return "";
  return cleaned.length <= maxLen ? cleaned : cleaned.slice(0, Math.max(0, maxLen - 3)).trimEnd() + "...";
}

export function limitList(items: string[], maxItems: number, maxLenEach: number): string[] {
  return items
    .map((item) => truncate(item, maxLenEach))
    .filter(Boolean)
    .slice(0, maxItems);
}

export function stanceLabel(stance: string): string {
  const cleaned = cleanText(stance);
  return STANCE_LABELS[cleaned.toLowerCase()] ?? cleaned;
}

export function hasMojibake(text: string): boolean {
  return /[�ÃÂ]|(?:鈥|锛|涓|绾|鐨|鏄|鍦|浠|乣|彿|€)/.test(text);
}
