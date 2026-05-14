import React from "react";
import { interpolate, Easing, useCurrentFrame } from "remotion";

import { STANCE_COLORS } from "./StancePie";
import {
  COLORS,
  FONTS,
  FW,
  getCardMaxHeight,
  glassCard,
  glassCardShadow,
  isCompactHeight,
  LAYOUT,
  S,
  sectionLabel,
} from "./design";
import { cleanText, ElementProps, stanceLabel, UI_TEXT } from "./utils";

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

function highlightKeywords(text: string, keywords: string[]): React.ReactNode {
  if (!text || keywords.length === 0) return text;
  const escaped = keywords
    .filter((k) => k.length > 1)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  if (escaped.length === 0) return text;
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);
  if (parts.length <= 1) return text;
  return parts.map((part, i) => {
    const isMatch = keywords.some((k) => k.toLowerCase() === part.toLowerCase());
    if (isMatch) {
      return (
        <span key={i} style={{ color: COLORS.accentLight, fontWeight: FW.heavy }}>
          {part}
        </span>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

// ── VS Badge ──────────────────────────────────────────────

const VsBadge: React.FC<{ frame: number; compact: boolean }> = ({ frame, compact }) => {
  const pulse = 1 + Math.sin(frame * 0.10) * 0.08;
  const glow = interpolate(Math.sin(frame * 0.10), [-1, 1], [0.25, 0.7]);
  const rotate = Math.sin(frame * 0.06) * 3;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        width: compact ? 52 : 64,
        zIndex: 2,
      }}
    >
      <div
        style={{
          width: compact ? 42 : 52,
          height: compact ? 42 : 52,
          borderRadius: "50%",
          background: `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.15), rgba(255,255,255,0.04))`,
          border: "1px solid rgba(255,255,255,0.15)",
          boxShadow: `0 0 ${compact ? 24 : 32}px rgba(255,255,255,${glow * 0.12})`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transform: `scale(${pulse}) rotate(${rotate}deg)`,
          backdropFilter: "blur(8px)",
        }}
      >
        <span
          style={{
            fontFamily: FONTS.mono,
            fontSize: compact ? 15 : 18,
            fontWeight: FW.heavy,
            color: "rgba(255,255,255,0.60)",
            letterSpacing: 2,
            lineHeight: 1,
          }}
        >
          VS
        </span>
      </div>
    </div>
  );
};

// ── Energy Bar ────────────────────────────────────────────

const EnergyBar: React.FC<{
  upvotes: number;
  maxUpvotes: number;
  color: string;
}> = ({ upvotes, maxUpvotes, color }) => {
  const pct = maxUpvotes > 0 ? Math.max(10, (upvotes / maxUpvotes) * 100) : 35;

  return (
    <div
      style={{
        height: 4,
        borderRadius: 2,
        background: "rgba(255,255,255,0.05)",
        overflow: "hidden",
        marginTop: 10,
        marginBottom: 12,
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          borderRadius: 2,
          background: `linear-gradient(90deg, ${color}66, ${color}CC)`,
          boxShadow: `0 0 8px ${color}33`,
        }}
      />
    </div>
  );
};

// ── Arena Column ──────────────────────────────────────────

const ArenaColumn: React.FC<{
  quote: Quote;
  side: "left" | "right";
  maxUpvotes: number;
  frame: number;
  compact: boolean;
  keywords: string[];
}> = ({ quote, side, maxUpvotes, frame, compact, keywords }) => {
  const progress = interpolate(frame, [9, 27], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;
  const { primaryText } = getQuoteText(quote);
  const upvotes = quote.upvotes ?? 0;
  const sideLabel = stanceLabel(quote.stance);

  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        opacity: progress,
        transform: `translateX(${interpolate(progress, [0, 1], [side === "left" ? -24 : 24, 0])}px)`,
        borderRadius: LAYOUT.panelRadius,
        background: `linear-gradient(160deg, ${stanceColor}0C, rgba(255,255,255,0.02))`,
        border: `1px solid ${stanceColor}20`,
        borderLeft: `3px solid ${stanceColor}`,
        padding: compact ? "14px 18px" : "20px 24px",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Stance label */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 4,
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontFamily: FONTS.sans,
            fontSize: compact ? 12 : 14,
            fontWeight: FW.heavy,
            color: stanceColor,
            letterSpacing: 0,
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 9,
              height: 9,
              borderRadius: "50%",
              backgroundColor: stanceColor,
              boxShadow: `0 0 10px ${stanceColor}55`,
            }}
          />
          {sideLabel}
        </span>
      </div>

      {/* Energy bar */}
      <EnergyBar upvotes={upvotes} maxUpvotes={maxUpvotes} color={stanceColor} />

      {/* Author */}
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: compact ? 11 : 12,
          fontWeight: FW.medium,
          color: COLORS.textTertiary,
          marginBottom: compact ? 10 : 12,
          overflow: "hidden",
          whiteSpace: "nowrap",
          textOverflow: "ellipsis",
        }}
      >
        {quote.author}
      </div>

      {/* Quote */}
      <div style={{ flex: 1 }}>
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: compact ? 14 : 15,
            color: COLORS.text,
            lineHeight: 1.75,
            fontWeight: FW.regular,
            letterSpacing: 0.2,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: compact ? 3 : 4,
            WebkitBoxOrient: "vertical" as const,
          }}
        >
          &ldquo;{highlightKeywords(primaryText, keywords)}&rdquo;
        </div>
      </div>

      {/* Upvote count */}
      {upvotes > 0 && (
        <div
          style={{
            marginTop: compact ? 10 : 12,
            fontFamily: FONTS.mono,
            fontSize: 10,
            fontWeight: FW.medium,
            color: "rgba(255,255,255,0.22)",
          }}
        >
          ▲ {upvotes}
        </div>
      )}
    </div>
  );
};

// ── Neutral Bar ──────────────────────────────────────────

const NeutralBar: React.FC<{
  quote: Quote;
  frame: number;
  compact: boolean;
  keywords: string[];
}> = ({ quote, frame, compact, keywords }) => {
  const progress = interpolate(frame, [16, 34], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;
  const { primaryText } = getQuoteText(quote);

  return (
    <div
      style={{
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [10, 0])}px)`,
        borderRadius: LAYOUT.panelRadius,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderLeft: `3px solid ${stanceColor}44`,
        padding: compact ? "12px 20px" : "16px 24px",
        boxSizing: "border-box",
        display: "flex",
        alignItems: "flex-start",
        gap: compact ? 14 : 18,
      }}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          fontFamily: FONTS.sans,
          fontSize: compact ? 11 : 12,
          fontWeight: FW.bold,
          color: stanceColor,
          backgroundColor: `${stanceColor}14`,
          borderRadius: LAYOUT.chipRadius,
          padding: "4px 10px",
          flexShrink: 0,
          marginTop: 2,
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: 6,
            height: 6,
            borderRadius: 3,
            backgroundColor: stanceColor,
          }}
        />
        {stanceLabel(quote.stance)}
      </span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: compact ? 11 : 12,
            fontWeight: FW.medium,
            color: COLORS.textTertiary,
            marginRight: 8,
          }}
        >
          {quote.author}
        </span>
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: compact ? 13 : 14,
            color: COLORS.text,
            lineHeight: 1.65,
            fontWeight: FW.regular,
            letterSpacing: 0.1,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
          }}
        >
          &ldquo;{highlightKeywords(primaryText, keywords)}&rdquo;
        </span>
      </div>
    </div>
  );
};

// ── Stats Bar ─────────────────────────────────────────────

const StatsBar: React.FC<{
  distribution: Record<string, number>;
  compact: boolean;
}> = ({ distribution, compact }) => {
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);
  if (entries.length === 0) return null;

  const total = entries.reduce((sum, [, v]) => sum + v, 0);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: compact ? 10 : 14,
        marginTop: compact ? 16 : 22,
      }}
    >
      <div
        style={{
          flex: 1,
          height: 4,
          borderRadius: 2,
          display: "flex",
          overflow: "hidden",
          gap: 2,
          background: "rgba(255,255,255,0.04)",
        }}
      >
        {entries.map(([label, value]) => {
          const color = STANCE_COLORS[label] || COLORS.textSecondary;
          const pct = total > 0 ? (value / total) * 100 : 0;
          return (
            <div
              key={label}
              style={{
                height: "100%",
                width: `${pct}%`,
                borderRadius: 2,
                background: `linear-gradient(90deg, ${color}88, ${color})`,
              }}
            />
          );
        })}
      </div>

      <div
        style={{
          display: "flex",
          gap: compact ? 10 : 14,
          flexShrink: 0,
        }}
      >
        {entries.map(([label, value]) => {
          const color = STANCE_COLORS[label] || COLORS.textSecondary;
          const pct = Math.round((value / (total || 1)) * 100);
          return (
            <span
              key={label}
              style={{
                fontFamily: FONTS.sans,
                fontSize: 10,
                fontWeight: FW.medium,
                color: COLORS.textTertiary,
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  width: 6,
                  height: 6,
                  borderRadius: 3,
                  backgroundColor: color,
                }}
              />
              {label} {pct}%
            </span>
          );
        })}
      </div>
    </div>
  );
};

// ── QuoteCard ─────────────────────────────────────────────

export const QuoteCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const quotes = ((elementProps.quotes as Quote[]) ?? []).slice(0, 3);
  const keywords = (elementProps.keywords as string[]) ?? [];
  const distribution = (elementProps.stance_distribution as Record<string, number>) ?? {};
  const debateFocus = (elementProps.debate_focus as string[]) ?? [];
  const compact = isCompactHeight(height);
  const cardW = width - LAYOUT.pageInset * 2;
  const cardMaxH = getCardMaxHeight(height);
  const topY = LAYOUT.topInset;

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (quotes.length === 0) {
    return null;
  }

  // Separate quotes by stance for arena layout
  const supportQuote = quotes.find((q) => q.stance === "支持");
  const opposeQuote = quotes.find((q) => q.stance === "质疑");
  const neutralQuote = quotes.find((q) => q.stance === "中立");

  const leftQuote = supportQuote || quotes[0];
  const rightQuote = opposeQuote || (quotes.length >= 2 ? quotes[1] : quotes[0]);
  const bottomQuote = neutralQuote || (quotes.length >= 3 ? quotes[2] : null);

  const maxUpvotes = Math.max(
    leftQuote?.upvotes ?? 0,
    rightQuote?.upvotes ?? 0,
    bottomQuote?.upvotes ?? 0,
  );

  // Build controversy question from debate_focus
  const controversyQuestion =
    debateFocus.length > 0 ? debateFocus[0] : "";

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        maxHeight: cardMaxH,
        ...glassCard,
        padding: compact ? "24px 32px" : "32px 40px",
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        overflow: "hidden",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: compact ? 8 : 10,
          gap: 16,
        }}
      >
        <div style={{ ...sectionLabel, marginBottom: 0 }}>{UI_TEXT.keyVoices}</div>
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: 10,
            fontWeight: FW.medium,
            color: "rgba(255,255,255,0.18)",
            letterSpacing: 0.3,
          }}
        >
          社区精选立场
        </span>
      </div>

      {/* ── Controversy question ── */}
      {controversyQuestion && (
        <div
          style={{
            textAlign: "center",
            padding: compact ? "8px 0 16px" : "10px 0 20px",
          }}
        >
          <span
            style={{
              display: "inline-block",
              fontFamily: FONTS.sans,
              fontSize: compact ? 13 : 15,
              fontWeight: FW.semibold,
              color: "rgba(255,255,255,0.28)",
              letterSpacing: 0.5,
              marginRight: 8,
            }}
          >
            核心争议
          </span>
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: compact ? 16 : 19,
              fontWeight: FW.heavy,
              color: COLORS.text,
              letterSpacing: 0.3,
              lineHeight: 1.4,
            }}
          >
            {controversyQuestion}
          </span>
        </div>
      )}

      {/* ── Arena: 支持 VS 质疑 ── */}
      <div
        style={{
          display: "flex",
          alignItems: "stretch",
          gap: 0,
        }}
      >
        <ArenaColumn
          quote={leftQuote}
          side="left"
          maxUpvotes={maxUpvotes}
          frame={frame}
          compact={compact}
          keywords={keywords}
        />

        <VsBadge frame={frame} compact={compact} />

        <ArenaColumn
          quote={rightQuote}
          side="right"
          maxUpvotes={maxUpvotes}
          frame={frame}
          compact={compact}
          keywords={keywords}
        />
      </div>

      {/* ── Neutral Bar ── */}
      {bottomQuote && (
        <div style={{ marginTop: compact ? 14 : 18 }}>
          <NeutralBar
            quote={bottomQuote}
            frame={frame}
            compact={compact}
            keywords={keywords}
          />
        </div>
      )}

      {/* ── Stats Bar ── */}
      <StatsBar distribution={distribution} compact={compact} />
    </div>
  );
};
