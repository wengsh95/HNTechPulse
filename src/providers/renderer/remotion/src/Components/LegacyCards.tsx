import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";

import { COLORS, FONTS, FW, S, useDesign } from "./design";
import { cleanText, ElementProps, p } from "./utils";

const EASE = Easing.bezier(0.16, 1, 0.3, 1);

function asNumber(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => cleanText(String(item))).filter(Boolean);
}

function textFrom(value: unknown): string {
  return cleanText(String(value ?? ""));
}

const fitLines = (lines: number): React.CSSProperties => ({
  overflow: "hidden",
  display: "-webkit-box",
  WebkitLineClamp: lines,
  WebkitBoxOrient: "vertical" as const,
});

const LegacyShell: React.FC<{
  width: number;
  height: number;
  label: string;
  accent?: string;
  children: React.ReactNode;
}> = ({ width, height: _height, label, accent = COLORS.accent, children }) => {
  const frame = useCurrentFrame();
  const d = useDesign();
  const progress = interpolate(frame, [4, 22], [0, 1], {
    easing: EASE,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const cardW = width - d.layout.pageInset * 2;

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        minHeight: d.getCardMaxHeight,
        padding: `${d.scaled(46)}px ${d.scaled(54)}px`,
        boxSizing: "border-box",
        borderRadius: d.scaled(16),
        background: "rgba(255,255,255,0.065)",
        boxShadow: "0 4px 24px rgba(0,0,0,0.40), 0 1px 6px rgba(0,0,0,0.25)",
        backdropFilter: "blur(40px) saturate(1.35)",
        WebkitBackdropFilter: "blur(40px) saturate(1.35)",
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [24, 0])}px)`,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: d.scaled(10),
          marginBottom: d.scaled(24),
        }}
      >
        <span
          style={{
            width: d.scaled(4),
            height: d.scaled(18),
            borderRadius: d.scaled(3),
            background: accent,
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.bodySmall,
            fontWeight: FW.heavy,
            color: COLORS.textSecondary,
            letterSpacing: 0,
          }}
        >
          {label}
        </span>
      </div>
      {children}
    </div>
  );
};

const Metric: React.FC<{ label: string; value: number; color?: string }> = ({
  label,
  value,
  color = COLORS.accentLight,
}) => {
  const d = useDesign();
  if (value <= 0) return null;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: d.scaled(6),
        height: d.scaled(32),
        padding: `0 ${d.scaled(14)}px`,
        borderRadius: d.scaled(999),
        background: "rgba(255,255,255,0.055)",
        border: `1px solid ${COLORS.borderLow}`,
        fontFamily: FONTS.mono,
        fontSize: d.fs.caption,
        fontWeight: FW.heavy,
        color,
      }}
    >
      <span style={{ color: COLORS.textTertiary }}>{label}</span>
      {value.toLocaleString("en-US")}
    </span>
  );
};

export const StoryHeaderCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const title = textFrom(
    elementProps.story_title ?? elementProps.title_cn ?? elementProps.source_title,
  );
  const score = asNumber(elementProps.score);
  const comments = asNumber(elementProps.comments ?? elementProps.comment_count);

  return (
    <LegacyShell width={width} height={height} label="Story Focus">
      <div
        style={{
          fontFamily: FONTS.bold,
          fontSize: d.fs.headline,
          fontWeight: FW.heavy,
          color: COLORS.text,
          lineHeight: 1.18,
          marginBottom: d.scaled(22),
          maxWidth: d.scaled(980),
          ...fitLines(3),
        }}
      >
        {title}
      </div>
      <div style={{ display: "flex", gap: d.scaled(10), flexWrap: "wrap" }}>
        <Metric label="score" value={score} />
        <Metric label="comments" value={comments} color={COLORS.brandLight} />
      </div>
    </LegacyShell>
  );
};

export const DiscussionOverviewCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const participants = asNumber(elementProps.participant_count);
  const depth = asNumber(elementProps.thread_depth_max);
  const active = textFrom(elementProps.active_duration);

  return (
    <LegacyShell width={width} height={height} label="Discussion Map" accent={COLORS.brand}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: d.scaled(18),
        }}
      >
        {[
          ["Participants", participants.toLocaleString("en-US")],
          ["Thread depth", depth.toLocaleString("en-US")],
          ["Active window", active || "-"],
        ].map(([label, value]) => (
          <div
            key={label}
            style={{
              padding: d.scaled(22),
              borderRadius: d.scaled(12),
              background: "rgba(255,255,255,0.045)",
              border: `1px solid ${COLORS.borderLow}`,
            }}
          >
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.caption,
                fontWeight: FW.bold,
                color: COLORS.textTertiary,
                marginBottom: d.scaled(8),
              }}
            >
              {label}
            </div>
            <div
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.subhead,
                fontWeight: FW.heavy,
                color: COLORS.text,
                lineHeight: 1,
              }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>
    </LegacyShell>
  );
};

export const CommentCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const author = textFrom(elementProps.author);
  const score = asNumber(elementProps.score);
  const label = textFrom(elementProps.angle_label);
  const translation = textFrom(elementProps.translation ?? elementProps.comment_translation);
  const original = textFrom(elementProps.text ?? elementProps.comment_text);

  return (
    <LegacyShell
      width={width}
      height={height}
      label={label || "Community Voice"}
      accent={COLORS.green}
    >
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: d.fs.subhead,
          fontWeight: FW.semibold,
          color: COLORS.text,
          lineHeight: 1.42,
          marginBottom: d.scaled(20),
          maxWidth: d.scaled(1000),
          ...fitLines(4),
        }}
      >
        &ldquo;{translation || original}&rdquo;
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: d.scaled(12),
          color: COLORS.textTertiary,
          fontFamily: FONTS.mono,
          fontSize: d.fs.bodySmall,
        }}
      >
        {author && <span>@{author}</span>}
        <Metric label="upvotes" value={score} color={COLORS.green} />
      </div>
    </LegacyShell>
  );
};

export const PerspectiveCompareCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const sides = [elementProps.perspective_a, elementProps.perspective_b].map((item) =>
    item && typeof item === "object" ? (item as Record<string, unknown>) : {},
  );

  return (
    <LegacyShell width={width} height={height} label="Two Perspectives" accent={COLORS.purple}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: d.scaled(20),
        }}
      >
        {sides.map((side, i) => {
          const label = textFrom(side.label) || `View ${i + 1}`;
          const body = textFrom(side.translation ?? side.text);
          const keywords = asStringArray(side.keywords);
          return (
            <div
              key={label}
              style={{
                minHeight: d.scaled(240),
                padding: d.scaled(24),
                borderRadius: d.scaled(12),
                background: i === 0 ? COLORS.accentBg : COLORS.brandBg,
                border: `1px solid ${i === 0 ? COLORS.accentBorderMid : COLORS.brandBorderSubtle}`,
              }}
            >
              <div
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: d.fs.bodyLg,
                  fontWeight: FW.heavy,
                  color: i === 0 ? COLORS.accentLight : COLORS.brandLight,
                  marginBottom: d.scaled(14),
                }}
              >
                {label}
              </div>
              <div
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: d.fs.body,
                  fontWeight: FW.medium,
                  color: COLORS.text,
                  lineHeight: 1.62,
                  ...fitLines(4),
                }}
              >
                {body}
              </div>
              {keywords.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    gap: d.scaled(8),
                    marginTop: d.scaled(18),
                    flexWrap: "wrap",
                  }}
                >
                  {keywords.slice(0, 3).map((kw) => (
                    <span
                      key={kw}
                      style={{
                        fontFamily: FONTS.mono,
                        fontSize: d.fs.caption,
                        color: COLORS.textSecondary,
                      }}
                    >
                      #{kw}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </LegacyShell>
  );
};

export const SynthesisCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const points = asStringArray(elementProps.points);

  return (
    <LegacyShell width={width} height={height} label="Synthesis" accent={COLORS.yellow}>
      <div style={{ display: "flex", flexDirection: "column", gap: d.scaled(14) }}>
        {points.slice(0, 4).map((point, i) => (
          <div
            key={point}
            style={{
              display: "flex",
              gap: d.scaled(14),
              alignItems: "baseline",
              padding: `${d.scaled(14)}px 0`,
              borderBottom: i < points.length - 1 ? `1px solid ${COLORS.borderLow}` : undefined,
            }}
          >
            <span
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.caption,
                fontWeight: FW.heavy,
                color: COLORS.yellow,
                flexShrink: 0,
              }}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.subhead,
                fontWeight: FW.semibold,
                color: COLORS.text,
                lineHeight: 1.35,
                ...fitLines(2),
              }}
            >
              {point}
            </span>
          </div>
        ))}
      </div>
    </LegacyShell>
  );
};

export const NewsCarouselCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const title = textFrom(elementProps.story_title);
  const comment = textFrom(elementProps.comment_translation ?? elementProps.comment_text);
  const author = textFrom(elementProps.author);
  const score = asNumber(elementProps.score);
  const comments = asNumber(elementProps.comment_count);

  return (
    <LegacyShell width={width} height={height} label="Quick News" accent={COLORS.orange}>
      <div
        style={{
          fontFamily: FONTS.bold,
          fontSize: d.fs.headline,
          fontWeight: FW.heavy,
          color: COLORS.text,
          lineHeight: 1.18,
          marginBottom: d.scaled(18),
          ...fitLines(2),
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: d.fs.bodyLg,
          color: COLORS.textBody,
          lineHeight: 1.65,
          marginBottom: d.scaled(20),
          maxWidth: d.scaled(960),
          ...fitLines(3),
        }}
      >
        {comment}
      </div>
      <div style={{ display: "flex", gap: d.scaled(10), alignItems: "center", flexWrap: "wrap" }}>
        {author && (
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.fs.bodySmall,
              color: COLORS.textTertiary,
            }}
          >
            @{author}
          </span>
        )}
        <Metric label="score" value={score} />
        <Metric label="comments" value={comments} color={COLORS.brandLight} />
      </div>
    </LegacyShell>
  );
};

export const PatternInsightCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const title = textFrom(elementProps.pattern_name);
  const description = textFrom(elementProps.description);
  const evidence = asStringArray(elementProps.evidence);

  return (
    <LegacyShell width={width} height={height} label="Insight" accent={COLORS.accentLight}>
      <div
        style={{
          fontFamily: FONTS.bold,
          fontSize: d.fs.headline,
          fontWeight: FW.heavy,
          color: COLORS.text,
          lineHeight: 1.18,
          marginBottom: d.scaled(18),
          ...fitLines(2),
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: d.fs.bodyLg,
          color: COLORS.textBody,
          lineHeight: 1.65,
          marginBottom: d.scaled(22),
          maxWidth: d.scaled(1000),
          ...fitLines(4),
        }}
      >
        {description}
      </div>
      <div style={{ display: "flex", gap: d.scaled(10), flexWrap: "wrap" }}>
        {evidence.slice(0, 4).map((item) => (
          <span
            key={item}
            style={{
              padding: `${d.scaled(7)}px ${d.scaled(14)}px`,
              borderRadius: d.scaled(999),
              background: COLORS.accentBg,
              border: `1px solid ${COLORS.accentBorderSubtle}`,
              color: COLORS.accentLight,
              fontFamily: FONTS.sans,
              fontSize: d.fs.caption,
              fontWeight: FW.bold,
            }}
          >
            {item}
          </span>
        ))}
      </div>
    </LegacyShell>
  );
};

export const OutroCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const d = useDesign();
  const title = p(elementProps, "text", "HN每日观察");
  const subtitle = p(elementProps, "subtitle", "See you next time");

  return (
    <LegacyShell width={width} height={height} label="Closing" accent={COLORS.brand}>
      <div
        style={{
          minHeight: d.scaled(300),
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontFamily: FONTS.bold,
            fontSize: d.fs.closing,
            fontWeight: FW.heavy,
            color: COLORS.text,
            lineHeight: 1.1,
            marginBottom: d.scaled(18),
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.bodyLg,
            fontWeight: FW.medium,
            color: COLORS.textSecondary,
          }}
        >
          {subtitle}
        </div>
      </div>
    </LegacyShell>
  );
};
