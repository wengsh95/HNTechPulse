import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

import {
  COLORS,
  FONTS,
  FW,
  glassCard,
  glassCardShadow,
  S,
  useChapterTone,
  useDesign,
} from "./design";
import {
  ChapterWatermark,
  GlassShimmer,
  dividerStyle,
  headerMargin,
  lineClamp,
  overshootTranslateY,
  titleFontSize,
  useCardAnimations,
  useCardPad,
  BODY_ENTRANCE_Y,
  CARD_ENTRANCE_Y,
  HEADER_ENTRANCE_Y,
  ITEM_DURATION,
} from "./HighlightShared";
import { cleanText, ElementProps, limitList, p } from "./utils";

type RoundupItem = {
  story_index?: number;
  display_index?: number;
  source_title?: string;
  display_title?: string;
  quick_label?: string;
  micro_takeaway?: string;
  source_domain?: string;
  score?: number;
  comment_count?: number;
  heat_level?: string;
  keywords?: string[];
};

const itemTitle = (item: RoundupItem) => cleanText(item.display_title || item.source_title || "");

const itemTakeaway = (item: RoundupItem) => cleanText(item.micro_takeaway || "");

/** Inline bar with leading icon + numeric value at right + filled track */
const ScoreBar: React.FC<{
  icon: string;
  value: number;
  /** 0..1, already grown over time */
  ratio: number;
  color: string;
  delay: number;
  frame: number;
}> = ({ icon, value, ratio, color, delay, frame }) => {
  const d = useDesign();
  const labelOpacity = interpolate(frame, [delay, delay + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: d.scaled(8),
        opacity: labelOpacity,
      }}
    >
      <span style={{ fontSize: d.fs.bodySmall, lineHeight: 1, flexShrink: 0 }}>{icon}</span>
      <div
        style={{
          flex: 1,
          height: d.scaled(6),
          borderRadius: 999,
          backgroundColor: COLORS.surfaceLow,
          overflow: "hidden",
          minWidth: d.scaled(40),
        }}
      >
        <div
          style={{
            width: `${Math.max(0, Math.min(1, ratio)) * 100}%`,
            height: "100%",
            backgroundColor: color,
            borderRadius: 999,
          }}
        />
      </div>
      <span
        style={{
          fontFamily: FONTS.mono,
          fontSize: d.fs.caption,
          fontWeight: FW.bold,
          color: COLORS.textSecondary,
          lineHeight: 1,
          minWidth: d.scaled(36),
          textAlign: "right",
          flexShrink: 0,
        }}
      >
        {value.toLocaleString("en-US")}
      </span>
    </div>
  );
};

const QuickRow: React.FC<{
  item: RoundupItem;
  index: number;
  frame: number;
  totalStories: number;
  maxScore: number;
  maxComments: number;
}> = ({ item, index, frame, totalStories, maxScore, maxComments }) => {
  const d = useDesign();
  const tone = useChapterTone();
  const compact = d.isCompactHeight;
  const delay = 10 + index * 3;
  const progress = interpolate(frame, [delay, delay + ITEM_DURATION], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const title = itemTitle(item);
  const takeaway = itemTakeaway(item);
  const displayIndex = Number(item.display_index ?? item.story_index ?? index) + 1;
  const score = Number(item.score || 0);
  const commentCount = Number(item.comment_count || 0);
  const domain = cleanText(item.source_domain || "");
  // Bar fill grows from 0 → final ratio over its own delay window
  const barGrow = interpolate(frame, [delay + 4, delay + 4 + 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scoreRatio = maxScore > 0 ? Math.min(1, score / maxScore) : 0;
  const commentRatio = maxComments > 0 ? Math.min(1, commentCount / maxComments) : 0;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `${d.scaled(54)}px minmax(0, 1fr) ${d.scaled(compact ? 140 : 180)}px`,
        gap: d.scaled(12),
        alignItems: "center",
        minHeight: d.scaled(94),
        padding: `${d.scaled(12)}px ${d.scaled(14)}px`,
        borderRadius: d.scaled(8),
        backgroundColor: COLORS.surfaceFaint,
        border: `1px solid ${COLORS.borderLow}`,
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [10, 0])}px)`,
      }}
    >
      <div
        style={{
          fontFamily: FONTS.mono,
          fontSize: d.fs.subtitle2,
          fontWeight: FW.heavy,
          color: COLORS.accentLight,
          lineHeight: 1,
          textAlign: "center",
        }}
      >
        {String(displayIndex).padStart(2, "0")}
        {totalStories > 0 && (
          <span
            style={{
              display: "block",
              marginTop: d.scaled(6),
              fontSize: d.fs.caption,
              color: COLORS.textFaint,
              fontWeight: FW.bold,
            }}
          >
            /{String(totalStories).padStart(2, "0")}
          </span>
        )}
      </div>

      <div style={{ minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: d.scaled(8),
            minWidth: 0,
          }}
        >
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.bodyLg,
              fontWeight: FW.heavy,
              color: COLORS.text,
              lineHeight: 1.25,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              ...lineClamp(2),
            }}
          >
            {title}
          </span>
          {domain && (
            <span
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.caption,
                color: COLORS.textFaint,
                lineHeight: 1.3,
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}
            >
              {domain}
            </span>
          )}
        </div>
        {takeaway && (
          <div
            style={{
              marginTop: d.scaled(5),
              fontFamily: FONTS.sans,
              fontSize: d.fs.bodySmall,
              fontWeight: FW.medium,
              color: COLORS.textSecondary,
              lineHeight: 1.45,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              ...lineClamp(1),
            }}
          >
            {takeaway}
          </div>
        )}
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
          justifyContent: "center",
          gap: d.scaled(8),
          minWidth: 0,
        }}
      >
        {score > 0 && (
          <ScoreBar
            icon="🔥"
            value={score}
            ratio={scoreRatio * barGrow}
            color={tone.accent}
            delay={delay + 2}
            frame={frame}
          />
        )}
        {commentCount > 0 && (
          <ScoreBar
            icon="💬"
            value={commentCount}
            ratio={commentRatio * barGrow}
            color={COLORS.textTertiary}
            delay={delay + 3}
            frame={frame}
          />
        )}
      </div>
    </div>
  );
};

export const QuickRoundupCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const frame = useCurrentFrame();
  const d = useDesign();
  const tone = useChapterTone();
  const compact = d.isCompactHeight;
  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress, footerProgress } = useCardAnimations(frame);

  const items = Array.isArray(elementProps.items)
    ? (elementProps.items as RoundupItem[]).slice(0, 4)
    : [];
  if (items.length === 0) {
    throw new Error("QuickRoundupCard requires items");
  }

  const displayIndex = Number(p(elementProps, "display_index", 0)) || 0;
  const storyCount = Number(p(elementProps, "story_count", 0)) || 0;
  const keywords = limitList(
    items.flatMap((item) => (Array.isArray(item.keywords) ? item.keywords : [])),
    3,
    14,
  );
  const showKeywordFooter = keywords.length > 0 && items.length < 4;
  const maxScore = items.reduce((m, it) => Math.max(m, Number(it.score || 0)), 0);
  const maxComments = items.reduce((m, it) => Math.max(m, Number(it.comment_count || 0)), 0);

  const cardW = width - d.layout.pageInset * 2;
  const cardH = d.getCardMaxHeight;
  const title = "快扫";
  const subtitle = `${items.length} 个值得留意的技术信号`;

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        minHeight: cardH,
        maxHeight: cardH,
        ...glassCard,
        boxShadow: glassCardShadow,
        padding: `${padY}px ${padX}px`,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, d.scaled(CARD_ENTRANCE_Y))}px)`,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <GlassShimmer frame={frame} />
      {storyCount > 0 && (
        <ChapterWatermark
          displayIndex={displayIndex + 1}
          storyCount={storyCount}
          padX={padX}
          padY={padY}
          frame={frame}
        />
      )}

      <div style={{ position: "relative", zIndex: 1 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(10),
            marginBottom: headerMargin(compact),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [HEADER_ENTRANCE_Y, 0])}px)`,
          }}
        >
          <div
            style={{
              width: d.scaled(3),
              height: d.scaled(14),
              borderRadius: 2,
              background: tone.accent,
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.bodySmall,
              fontWeight: FW.semibold,
              color: tone.labelText,
              letterSpacing: 0.4,
            }}
          >
            快扫
          </span>
        </div>

        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: titleFontSize(d, compact),
            color: COLORS.text,
            lineHeight: 1.1,
            letterSpacing: 0,
            opacity: titleProgress,
          }}
        >
          {title}
        </div>
        <div
          style={{
            marginTop: d.scaled(8),
            marginBottom: d.scaled(compact ? 18 : 24),
            fontFamily: FONTS.sans,
            fontSize: d.fs.bodyLg,
            fontWeight: FW.medium,
            color: COLORS.textSecondary,
            lineHeight: 1.35,
            opacity: titleProgress,
          }}
        >
          {subtitle}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr",
            gap: d.scaled(compact ? 8 : 9),
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
          }}
        >
          {items.map((item, i) => (
            <QuickRow
              key={`${item.story_index ?? i}-${item.source_title ?? i}`}
              item={item}
              index={i}
              frame={frame}
              totalStories={storyCount}
              maxScore={maxScore}
              maxComments={maxComments}
            />
          ))}
        </div>
      </div>

      <div style={{ flex: 1, minHeight: d.scaled(18) }} />
      {showKeywordFooter && (
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={dividerStyle} />
          <div
            style={{
              display: "flex",
              gap: d.scaled(8),
              opacity: footerProgress,
            }}
          >
            {keywords.map((keyword) => (
              <span
                key={keyword}
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: d.fs.caption,
                  fontWeight: FW.bold,
                  color: COLORS.textTertiary,
                  backgroundColor: COLORS.surfaceFaint,
                  border: `1px solid ${COLORS.borderLow}`,
                  borderRadius: d.scaled(4),
                  padding: `${d.scaled(3)}px ${d.scaled(8)}px`,
                }}
              >
                {keyword}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
