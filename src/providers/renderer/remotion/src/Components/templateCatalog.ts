type ShotTemplateMetadata = {
  template_id: string;
  label: string;
  intent: string;
  chapter: "cover" | "focus" | "atmosphere" | "closing";
  required_props: readonly string[];
  optional_props: readonly string[];
  min_duration_sec: number;
  max_lines?: number;
};

/**
 * Human/editor-facing catalog of renderable shot templates.
 *
 * Keep this catalog small and semantic: templates describe visual intent,
 * while story-specific content remains in element props.
 */
export const SHOT_TEMPLATE_CATALOG = {
  cover_card: {
    template_id: "cover_v1",
    label: "封面",
    intent: "daily brief cover",
    chapter: "cover",
    required_props: ["headline"],
    optional_props: ["date_label", "highlight_entries", "section_counts"],
    min_duration_sec: 4,
  },
  headline_card: {
    template_id: "headline_v1",
    label: "头条钩子",
    intent: "large editorial hook",
    chapter: "focus",
    required_props: ["title"],
    optional_props: ["eyebrow", "subtitle", "stat", "stat_label", "source_label"],
    min_duration_sec: 3,
    max_lines: 4,
  },
  event_card: {
    template_id: "event_v1",
    label: "事件卡",
    intent: "event summary",
    chapter: "focus",
    required_props: [],
    optional_props: ["editor_angle", "key_points", "image_src"],
    min_duration_sec: 5,
  },
  source_evidence_card: {
    template_id: "source_evidence_v1",
    label: "来源证据",
    intent: "article or source evidence",
    chapter: "focus",
    required_props: ["title"],
    optional_props: ["image_url", "source_url", "caption", "highlights"],
    min_duration_sec: 4,
    max_lines: 6,
  },
  atmosphere_card: {
    template_id: "discussion_v1",
    label: "讨论气氛",
    intent: "discussion summary",
    chapter: "atmosphere",
    required_props: [],
    optional_props: ["discussion_summary", "quotes", "stance_distribution"],
    min_duration_sec: 5,
  },
  comment_card: {
    template_id: "comment_single_v1",
    label: "单条评论",
    intent: "one HN community viewpoint",
    chapter: "atmosphere",
    required_props: ["quote"],
    optional_props: ["author", "stance", "source_url"],
    min_duration_sec: 3,
    max_lines: 5,
  },
  comment_dual_card: {
    template_id: "comment_dual_v1",
    label: "评论对照",
    intent: "two-sided community debate",
    chapter: "atmosphere",
    required_props: ["left_summary", "right_summary"],
    optional_props: ["left_label", "right_label", "title", "note"],
    min_duration_sec: 4,
    max_lines: 5,
  },
  data_number_card: {
    template_id: "data_number_v1",
    label: "数据冲击",
    intent: "one concrete number",
    chapter: "focus",
    required_props: ["value", "label"],
    optional_props: ["context", "comparisons", "source_url"],
    min_duration_sec: 3,
    max_lines: 4,
  },
  quick_card: {
    template_id: "quick_news_v1",
    label: "快讯",
    intent: "one-fact quick news beat",
    chapter: "focus",
    required_props: ["title", "fact"],
    optional_props: ["index", "comment_focus", "source_url"],
    min_duration_sec: 3,
    max_lines: 5,
  },
  closing_card: {
    template_id: "closing_v1",
    label: "结尾",
    intent: "closing summary",
    chapter: "closing",
    required_props: [],
    optional_props: ["takeaways", "summary_items", "signal"],
    min_duration_sec: 5,
  },
  signals_card: {
    template_id: "closing_signals_v1",
    label: "三条信号",
    intent: "three concise closing signals",
    chapter: "closing",
    required_props: ["items"],
    optional_props: ["title"],
    min_duration_sec: 5,
    max_lines: 3,
  },
} as const satisfies Record<string, ShotTemplateMetadata>;

export type ShotTemplateElementType = keyof typeof SHOT_TEMPLATE_CATALOG;
