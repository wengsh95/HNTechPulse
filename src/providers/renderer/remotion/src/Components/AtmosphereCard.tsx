import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { StancePie, STANCE_COLORS } from "./StancePie";
import {
  COLORS,
  FONTS,
  FW,
  FS,
  getCardMaxHeight,
  glassCard,
  glassCardShadow,
  isCompactHeight,
  LAYOUT,
  S,
} from "./design";
import {
  audioPulse,
  CapsuleBadge,
  dividerStyle,
  GlassShimmer,
  highlightKeywords,
  KeywordTag,
  lineClamp,
  overshootTranslateY,
  SectionLabel,
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
  text: string;
  text_cn?: string;
  stance: string;
  upvotes?: number;
}

function getQuoteText(quote: Quote) {
  const hasChinese = Boolean(quote.text_cn?.trim());
  return {
    primaryText: hasChinese ? cleanText(quote.text_cn!.trim()) : cleanText(quote.text),
  };
}

const ControversyPill: React.FC<{
  score: number;
  delay: number;
  frame: number;
}> = ({ score, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + 14], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const color = getControversyColor(score);
  const label = getControversyLabel(score);
  const pulse = audioPulse(frame);

  return (
    <span
      style={{
        fontFamily: FONTS.sans,
        fontSize: FS.pill,
        fontWeight: FW.bold,
        color: COLORS.white,
        background: `linear-gradient(135deg, ${color} 0%, ${color}BB 100%)`,
        borderRadius: 999,
        padding: "3px 12px",
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
  const progress = interpolate(frame, [delay, delay + 18], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 6,
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [6, 0])}px)`,
      }}
    >
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: FS.label,
          fontWeight: FW.bold,
          color: COLORS.accentLight,
          opacity: 0.7,
          flexShrink: 0,
          lineHeight: 1.7,
        }}
      >
        {String(index + 1).padStart(2, "0")}
      </span>
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: FS.bodySmall,
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

const QuoteRow: React.FC<{
  quote: Quote;
  index: number;
  frame: number;
  compact: boolean;
  keywords: string[];
}> = ({ quote, index, frame, compact, keywords }) => {
  const delay = 16 + index * 5;
  const progress = interpolate(frame, [delay, delay + 18], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const { primaryText } = getQuoteText(quote);
  const upvotes = quote.upvotes ?? 0;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [6, 0])}px)`,
      }}
    >
      <span
        style={{
          display: "inline-block",
          width: 7,
          height: 7,
          borderRadius: "50%",
          backgroundColor: STANCE_COLORS[quote.stance] || COLORS.textSecondary,
          flexShrink: 0,
          marginTop: 6,
        }}
      />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 6,
            marginBottom: 2,
          }}
        >
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: FS.caption,
              fontWeight: FW.bold,
              color: COLORS.textTertiary,
            }}
          >
            {quote.author}
          </span>
          {upvotes > 0 && (
            <span
              style={{
                fontFamily: FONTS.mono,
                fontSize: FS.micro,
                fontWeight: FW.medium,
                color: COLORS.textFaint,
              }}
            >
              ▲ {upvotes}
            </span>
          )}
        </div>

        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: compact ? FS.bodySmall : FS.body,
            color: COLORS.text,
            lineHeight: 1.7,
            fontWeight: FW.regular,
            letterSpacing: 0.1,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            ...lineClamp(compact ? 2 : 3),
          }}
        >
          &ldquo;{highlightKeywords(primaryText, keywords, frame, delay)}&rdquo;
        </div>
      </div>
    </div>
  );
};

export const AtmosphereCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const stanceDistribution = (elementProps.stance_distribution as Record<string, number>) ?? {};
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

  // Quote data (merged from QuoteCard)
  const quotes = ((elementProps.quotes as Quote[]) ?? []).slice(0, 2);

  const hasPie = Object.keys(compactStances).length > 0;
  const hasFocus = debateFocus.length > 0;
  const hasQuotes = quotes.length > 0;

  const compact = isCompactHeight(height);
  const cardW = width - LAYOUT.pageInset * 2;
  const cardMaxH = getCardMaxHeight(height);

  const padX = compact ? 36 : 44;
  const padY = compact ? 32 : 40;
  const pieW = hasPie ? (compact ? 200 : 280) : 0;
  const gap = hasPie ? (compact ? 20 : 28) : 0;
  const textColW = hasPie
    ? Math.max(280, cardW - pieW - gap - padX * 2)
    : Math.min(cardW - padX * 2, LAYOUT.contentWideMaxWidth);

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const titleProgress = interpolate(frame, [8, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const bodyProgress = interpolate(frame, [14, 32], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const imageProgress = interpolate(frame, [6, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const footerProgress = interpolate(frame, [20, 36], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const hasFooter = keywords.length > 0;
  const titleFontSize = compact ? 34 : FS.headline;

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: LAYOUT.topInset,
        width: cardW,
        minHeight: cardMaxH,
        ...glassCard,
        padding: `${padY}px ${padX}px`,
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, 28)}px)`,
        display: "flex",
        gap,
        alignItems: "stretch",
        overflow: "visible",
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
        }}
      >
        {/* Header row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: compact ? 16 : 20,
            maxWidth: textColW,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [6, 0])}px)`,
          }}
        >
          <CapsuleBadge text="讨论氛围" />
        </div>

        {/* Controversy score */}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 10,
            marginBottom: compact ? 8 : 10,
            maxWidth: textColW,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          <span
            style={{
              fontFamily: FONTS.bold,
              fontSize: titleFontSize,
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
              fontSize: FS.subtitle2,
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
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [8, 0])}px)`,
            }}
          >
            <SectionLabel text={UI_TEXT.debateFocus} delay={18} frame={frame} />
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: compact ? 4 : 6,
                marginBottom: hasQuotes ? (compact ? 10 : 12) : 0,
                maxWidth: textColW,
              }}
            >
              {debateFocus.slice(0, 3).map((focus, i) => (
                <FocusPoint key={focus} index={i} text={focus} delay={20 + i * 5} frame={frame} />
              ))}
            </div>
          </div>
        )}

        {/* Quotes (merged from QuoteCard, max 2) */}
        {hasQuotes && (
          <div
            style={{
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [8, 0])}px)`,
            }}
          >
            <SectionLabel text="精选观点" delay={14} frame={frame} />

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: compact ? 6 : 8,
                marginBottom: hasFooter ? (compact ? 10 : 12) : 0,
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
                />
              ))}
            </div>
          </div>
        )}

        {/* Keywords */}
        {hasFooter && <div style={dividerStyle} />}
        {keywords.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "flex-start",
              gap: 6,
              opacity: footerProgress,
            }}
          >
            {keywords.map((kw, i) => (
              <KeywordTag key={kw} keyword={kw} delay={22 + i * 4} frame={frame} />
            ))}
          </div>
        )}
      </div>

      {/* Right: stance pie chart */}
      {hasPie && (
        <div
          style={{
            flex: `0 0 ${pieW}px`,
            alignSelf: "flex-start",
            marginLeft: -100,
            overflow: "visible",
            opacity: imageProgress,
            transform: `translateX(${interpolate(imageProgress, [0, 1], [24, 0])}px)`,
          }}
        >
          <StancePie
            distribution={compactStances}
            size={compact ? 250 : 500}
            centerLabel={commentCount > 0 ? `${commentCount}条` : undefined}
          />
        </div>
      )}
    </div>
  );
};
