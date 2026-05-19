import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { StancePie, STANCE_COLORS } from "./StancePie";
import { COLORS, FONTS, FW, useDesign, glassCard, glassCardShadow, S } from "./design";
import {
  audioPulse,
  dividerStyle,
  GlassShimmer,
  highlightKeywords,
  lineClamp,
  overshootTranslateY,
  SectionLabel,
  useCardPad,
  useCardAnimations,
  headerMargin,
  titleBodyGap,
  bodySectionGap,
  titleFontSize,
  CardKeywordsFooter,
  CARD_ENTRANCE_Y,
  BODY_ENTRANCE_Y,
  IMAGE_ENTRANCE_X,
  ITEM_DURATION,
  PILL_DURATION,
} from "./HighlightShared";
import { cleanText, ElementProps, limitList, p, UI_TEXT } from "./utils";

const CONTROVERSY_COLORS = {
  green: COLORS.green,
  yellow: COLORS.yellow,
  red: COLORS.orangeRed,
};

function getControversyColor(score: number): string {
  if (score <= 3) return CONTROVERSY_COLORS.green;
  if (score <= 7) return CONTROVERSY_COLORS.yellow;
  return CONTROVERSY_COLORS.red;
}

function getControversyLabel(score: number): string {
  if (score <= 3) return "共识较强";
  if (score <= 7) return "存在分歧";
  return "高度争议";
}

function compactDistribution(distribution: Record<string, number>): Record<string, number> {
  const entries = Object.entries(distribution)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);
  const top = entries.slice(0, 3);
  const rest = entries.slice(3).reduce((sum, [, value]) => sum + value, 0);
  return Object.fromEntries(rest > 0 ? [...top, ["其他", rest]] : top);
}

interface Quote {
  author: string;
  display_text: string;
  stance: string;
  upvotes?: number;
}

function getQuoteText(quote: Quote) {
  if (!quote.display_text?.trim()) {
    throw new Error("AtmosphereCard quote requires display_text");
  }
  return {
    primaryText: cleanText(quote.display_text.trim()),
  };
}

const ControversyPill: React.FC<{
  score: number;
  delay: number;
  frame: number;
}> = ({ score, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + PILL_DURATION], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const { fs, scaled } = useDesign();
  const color = getControversyColor(score);
  const label = getControversyLabel(score);
  const pulse = audioPulse(frame);

  return (
    <span
      style={{
        fontFamily: FONTS.sans,
        fontSize: fs.pill,
        fontWeight: FW.bold,
        color: COLORS.white,
        background: `linear-gradient(135deg, ${color} 0%, ${color}BB 100%)`,
        borderRadius: 999,
        padding: `${scaled(4)}px ${scaled(14)}px`,
        letterSpacing: 0.3,
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [4, 0])}px) scale(${1 + pulse * 0.03})`,
      }}
    >
      {label}
    </span>
  );
};

const FocusPoint: React.FC<{
  index: number;
  text: string;
  delay: number;
  frame: number;
}> = ({ index, text, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + ITEM_DURATION], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const { fs, scaled } = useDesign();

  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: scaled(10),
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [6, 0])}px)`,
      }}
    >
      <span
        style={{
          fontFamily: FONTS.mono,
          fontSize: fs.caption,
          fontWeight: FW.bold,
          color: COLORS.accentLight,
          backgroundColor: COLORS.accentBg,
          borderRadius: scaled(4),
          padding: `${scaled(2)}px ${scaled(6)}px`,
          flexShrink: 0,
          lineHeight: 1.4,
          minWidth: scaled(24),
          textAlign: "center",
        }}
      >
        {String(index + 1).padStart(2, "0")}
      </span>
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: fs.body,
          fontWeight: FW.medium,
          color: COLORS.textSecondary,
          lineHeight: 1.7,
          overflowWrap: "anywhere",
          wordBreak: "break-word",
        }}
      >
        {text}
      </span>
    </div>
  );
};

const UpvoteBadge: React.FC<{
  upvotes: number;
}> = ({ upvotes }) => {
  const { fs, scaled } = useDesign();
  return (
    <span
      style={{
        fontFamily: FONTS.mono,
        fontSize: fs.caption,
        fontWeight: FW.bold,
        color: COLORS.orange,
        lineHeight: 1,
        display: "inline-flex",
        alignItems: "center",
        gap: scaled(3),
        backgroundColor: COLORS.surfaceFaint,
        borderRadius: scaled(4),
        padding: `${scaled(2)}px ${scaled(8)}px`,
      }}
    >
      <span style={{ fontSize: fs.caption }}>▲</span>
      {upvotes.toLocaleString("en-US")}
    </span>
  );
};

const QuoteRow: React.FC<{
  quote: Quote;
  index: number;
  frame: number;
  compact: boolean;
  keywords: string[];
  dense?: boolean;
}> = ({ quote, index, frame, compact, keywords, dense = false }) => {
  const { fs, scaled } = useDesign();
  const delay = 16 + index * 5;
  const progress = interpolate(frame, [delay, delay + ITEM_DURATION], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const { primaryText } = getQuoteText(quote);
  const showUpvotes = (quote.upvotes || 0) > 0;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: scaled(10),
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [6, 0])}px)`,
        backgroundColor: COLORS.surfaceFaint,
        borderRadius: scaled(8),
        padding: `${scaled(dense ? 8 : compact ? 10 : 14)}px ${scaled(compact ? 12 : 16)}px`,
        borderLeft: `${scaled(3)}px solid ${STANCE_COLORS[quote.stance] || COLORS.textSecondary}`,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: fs.body,
            color: COLORS.text,
            lineHeight: dense ? 1.5 : 1.7,
            fontWeight: FW.regular,
            letterSpacing: 0.1,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            ...lineClamp(dense ? 2 : compact ? 2 : 3),
          }}
        >
          &ldquo;{highlightKeywords(primaryText, keywords, frame, delay)}&rdquo;
        </div>
        <div
          style={{
            marginTop: scaled(6),
            display: "flex",
            alignItems: "center",
            gap: scaled(8),
            flexWrap: "wrap",
          }}
        >
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: fs.body,
              fontWeight: FW.regular,
              color: COLORS.textFaint,
              lineHeight: 1.4,
            }}
          >
            — {quote.author}
          </span>
          {showUpvotes && <UpvoteBadge upvotes={quote.upvotes || 0} />}
        </div>
      </div>
    </div>
  );
};

export const AtmosphereCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const stanceDistribution = (elementProps.stance_distribution as Record<string, number>) ?? {};
  const stanceConcerns = (elementProps.stance_concerns as Record<string, string>) ?? {};
  const debateFocus = (elementProps.debate_focus as string[]) ?? [];
  const keywords = limitList(
    Array.isArray(elementProps.keywords)
      ? elementProps.keywords.filter((k): k is string => typeof k === "string")
      : [],
    4,
    16,
  );

  const controversyScore = p(elementProps, "controversy_score", 0);
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const scoreNum =
    typeof controversyScore === "number" ? controversyScore : Number(controversyScore) || 0;
  const compactStances = compactDistribution(stanceDistribution);

  const quotes = ((elementProps.quotes as Quote[]) ?? []).slice(0, 3);

  const hasPie = Object.keys(compactStances).length > 0;
  const hasFocus = debateFocus.length > 0;
  const hasQuotes = quotes.length > 0;

  const d = useDesign();
  const compact = d.isCompactHeight;
  const cardW = width - d.layout.pageInset * 2;
  const cardMaxH = d.getCardMaxHeight;

  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress, imageProgress, footerProgress } =
    useCardAnimations(frame);

  const gap = hasPie ? d.scaled(compact ? 20 : 28) : 0;
  const pieSize = d.scaled(compact ? 130 : 200);
  const availableTextW = cardW - pieSize - gap - padX * 2;
  const textColW = hasPie
    ? Math.max(d.scaled(360), Math.min(availableTextW, cardW - padX * 2))
    : Math.min(cardW - padX * 2, d.layout.contentWideMaxWidth);

  const hasFooter = keywords.length > 0;
  const resolvedTitleFontSize = titleFontSize(d, compact);

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        minHeight: cardMaxH,
        maxHeight: cardMaxH,
        ...glassCard,
        background: `linear-gradient(135deg, rgba(255,102,0,0.035), rgba(255,255,255,0.055) 38%, rgba(52,199,89,0.03))`,
        padding: `${padY}px ${padX}px`,
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, d.scaled(CARD_ENTRANCE_Y))}px)`,
        display: "flex",
        gap,
        alignItems: "stretch",
        overflow: "hidden",
      }}
    >
      <GlassShimmer frame={frame} />
      <div
        style={{
          flex: hasPie ? `0 0 ${textColW}px` : 1,
          maxWidth: textColW,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          position: "relative",
          zIndex: 1,
          alignSelf: hasPie ? undefined : "center",
        }}
      >
        {/* Header row */}
        <SectionLabel text="社区回声" delay={8} frame={frame} variant="brand" />

        {/* Controversy score */}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: d.scaled(10),
            marginBottom: compact ? d.scaled(8) : d.scaled(14),
            maxWidth: textColW,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          <span
            style={{
              fontFamily: FONTS.bold,
              fontSize: resolvedTitleFontSize,
              fontWeight: FW.heavy,
              color: COLORS.text,
              lineHeight: 1.15,
              letterSpacing: -0.4,
            }}
          >
            {scoreNum.toFixed(1)}
          </span>
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.subtitle2,
              fontWeight: FW.regular,
              color: COLORS.textTertiary,
              lineHeight: 1.4,
            }}
          >
            /10 争议度
          </span>
          <ControversyPill score={scoreNum} delay={10} frame={frame} />
        </div>

        {/* Debate focus */}
        {hasFocus && (
          <div
            style={{
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
            }}
          >
            <SectionLabel text={UI_TEXT.debateFocus} delay={18} frame={frame} variant="default" />
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: d.scaled(compact ? 4 : 8),
                marginBottom: hasQuotes ? bodySectionGap(compact) : 0,
                maxWidth: textColW,
              }}
            >
              {debateFocus.slice(0, 3).map((focus, i) => (
                <FocusPoint key={focus} index={i} text={focus} delay={20 + i * 5} frame={frame} />
              ))}
            </div>
          </div>
        )}

        {/* Quotes */}
        {hasQuotes && (
          <div
            style={{
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
            }}
          >
            <SectionLabel text="精选观点" delay={14} frame={frame} variant="success" />

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: d.scaled(quotes.length >= 3 ? 5 : compact ? 6 : 10),
                marginBottom: hasFooter ? bodySectionGap(compact) : 0,
                maxWidth: textColW,
              }}
            >
              {quotes.map((quote, i) => (
                <QuoteRow
                  key={`${quote.author}-${i}`}
                  quote={quote}
                  index={i}
                  frame={frame}
                  compact={compact}
                  keywords={keywords}
                  dense={quotes.length >= 3}
                />
              ))}
            </div>
          </div>
        )}

        {/* Keywords */}
        {hasFooter && <div style={dividerStyle} />}
        {keywords.length > 0 && (
          <CardKeywordsFooter
            keywords={keywords}
            progress={footerProgress}
            frame={frame}
            delayBase={22}
          />
        )}
      </div>

      {/* Right: stance pie chart */}
      {hasPie && (
        <div
          style={{
            flex: `0 0 ${pieSize}px`,
            alignSelf: "stretch",
            overflow: "visible",
            opacity: imageProgress,
            transform: `translateX(${interpolate(imageProgress, [0, 1], [IMAGE_ENTRANCE_X, 0])}px)`,
            paddingTop: d.scaled(24),
            paddingLeft: d.scaled(24),
            borderLeft: `1px solid ${COLORS.borderLow}`,
          }}
        >
          <StancePie
            distribution={compactStances}
            size={pieSize}
            centerLabel={commentCount > 0 ? `${commentCount}条` : undefined}
            stanceConcerns={stanceConcerns}
            quotedStances={quotes.map((q) => q.stance).filter(Boolean)}
          />
        </div>
      )}
    </div>
  );
};
