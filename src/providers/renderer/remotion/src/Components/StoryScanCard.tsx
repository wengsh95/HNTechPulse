import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing, spring } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, S } from "./design";

const STANCE_COLORS: Record<string, string> = {
  "支持": "#007aff",
  "质疑": "#ff3b30",
  "中立": "#8e8e93",
  "调侃": "#ff9500",
  "担忧": "#5856d6",
};

const StancePie: React.FC<{ distribution: Record<string, number>; size: number }> = ({ distribution, size }) => {
  const frame = useCurrentFrame();
  const cx = size / 2;
  const cy = size / 2;
  const outerR = size / 2 - 6;
  const innerR = outerR * 0.68;
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);

  // Pie draw-in animation
  const pieProgress = interpolate(frame, [8, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  let cumulative = 0;
  const arcs = entries.map(([label, value]) => {
    const startAngle = cumulative * 2 * Math.PI;
    cumulative += value;
    const endAngle = cumulative * 2 * Math.PI;
    const largeArc = value > 0.5 ? 1 : 0;

    const outerX1 = cx + outerR * Math.cos(startAngle - Math.PI / 2);
    const outerY1 = cy + outerR * Math.sin(startAngle - Math.PI / 2);
    const outerX2 = cx + outerR * Math.cos(endAngle - Math.PI / 2);
    const outerY2 = cy + outerR * Math.sin(endAngle - Math.PI / 2);
    const innerX1 = cx + innerR * Math.cos(startAngle - Math.PI / 2);
    const innerY1 = cy + innerR * Math.sin(startAngle - Math.PI / 2);
    const innerX2 = cx + innerR * Math.cos(endAngle - Math.PI / 2);
    const innerY2 = cy + innerR * Math.sin(endAngle - Math.PI / 2);

    const path = `M ${outerX1} ${outerY1} A ${outerR} ${outerR} 0 ${largeArc} 1 ${outerX2} ${outerY2} L ${innerX2} ${innerY2} A ${innerR} ${innerR} 0 ${largeArc} 0 ${innerX1} ${innerY1} Z`;
    const color = STANCE_COLORS[label] || COLORS.dim;
    return { label, value, path, color };
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, opacity: pieProgress }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {arcs.map((arc, i) => (
          <path
            key={i}
            d={arc.path}
            fill={arc.color}
            stroke="rgba(255,255,255,0.6)"
            strokeWidth={2}
          />
        ))}
      </svg>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "6px 14px",
          marginTop: 12,
          justifyContent: "center",
        }}
      >
        {entries.map(([label, value]) => {
          const color = STANCE_COLORS[label] || COLORS.dim;
          return (
            <span
              key={label}
              style={{
                fontFamily: FONTS.sans,
                fontSize: 13,
                fontWeight: 500,
                color: COLORS.text,
                display: "flex",
                alignItems: "center",
                gap: 6,
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
              {label} {Math.round(value * 100)}%
            </span>
          );
        })}
      </div>
    </div>
  );
};

export const StoryScanCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const storyTitle = p(elementProps, "story_title", "");
  const titleCn = p(elementProps, "title_cn", "");
  const eventSummary = p(elementProps, "event_summary", "");
  const displayIndex = p(elementProps, "display_index", -1);
  const storyCount = p(elementProps, "story_count", 0);
  const viewpoints = (elementProps.viewpoints as Array<{
    stance?: string;
    summary?: string;
    quote?: string;
    quote_cn?: string;
  }>) ?? [];
  const stanceDistribution = elementProps.stance_distribution as Record<string, number> | undefined;

  const cardW = width - 160;
  const hasPie = stanceDistribution && Object.keys(stanceDistribution).length > 0;
  const vpCount = viewpoints.length;
  const showProgress = storyCount > 1 && displayIndex >= 0;

  // Dynamic vertical centering based on estimated content height
  const titleAreaH = titleCn ? 100 : 70;
  const contentAreaEstimate = vpCount > 0 ? 40 + vpCount * 95 : 0;
  const estimatedCardH = titleAreaH + contentAreaEstimate + 80;
  const topY = Math.max(56, Math.round((height - estimatedCardH) / 2));

  // Card entrance: spring for bouncy feel
  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  return (
    <div
      style={{
        ...S,
        left: 80,
        top: topY,
        width: cardW,
        background: "#ffffff",
        borderRadius: 24,
        padding: "36px 48px 36px",
        boxShadow:
          "0 0 0 0.5px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04), 0 8px 32px rgba(0,0,0,0.07)",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      {/* Progress indicator */}
      {showProgress && (
        <div
          style={{
            position: "absolute",
            top: 18,
            right: 24,
            fontFamily: FONTS.mono,
            fontSize: 13,
            fontWeight: 600,
            color: COLORS.dim,
            backgroundColor: COLORS.borderLight,
            borderRadius: 10,
            padding: "3px 12px",
            letterSpacing: 0.4,
          }}
        >
          {displayIndex + 1} / {storyCount}
        </div>
      )}

      {/* Title */}
      <div
        style={{
          fontFamily: FONTS.bold,
          fontWeight: 700,
          fontSize: 32,
          color: COLORS.text,
          lineHeight: 1.2,
          letterSpacing: -0.6,
          paddingRight: showProgress ? 70 : 0,
        }}
      >
        {titleCn || storyTitle}
      </div>
      {titleCn && storyTitle && (
        <div
          style={{
            fontFamily: FONTS.sans,
            fontWeight: 500,
            fontSize: 18,
            color: COLORS.dim,
            marginTop: 6,
            lineHeight: 1.3,
          }}
        >
          {storyTitle}
        </div>
      )}

      {/* Event summary */}
      {eventSummary && (
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: 20,
            color: COLORS.textLight,
            marginTop: 16,
            lineHeight: 1.5,
            fontWeight: 400,
          }}
        >
          {eventSummary}
        </div>
      )}

      {/* Viewpoints */}
      {viewpoints.length > 0 && (
        <>
          <div
            style={{
              height: "0.5px",
              backgroundColor: "rgba(0,0,0,0.06)",
              margin: "20px 0 18px",
            }}
          />
          <div style={{ display: "flex", gap: 32 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 11,
                  fontWeight: 600,
                  color: COLORS.dim,
                  marginBottom: 16,
                  textTransform: "uppercase",
                  letterSpacing: 0.8,
                }}
              >
                社区观点
              </div>
              {viewpoints.map((vp, i) => {
                const stance = vp.stance || "";
                const summary = vp.summary || "";
                const quote = vp.quote || "";
                const quote_cn = vp.quote_cn || "";
                const stanceColor = STANCE_COLORS[stance] || COLORS.dim;

                // Spring-based staggered entrance
                const vpProgress = spring({
                  frame,
                  fps,
                  config: { damping: 12, stiffness: 110 },
                  delay: 8 + i * 5,
                });

                return (
                  <div
                    key={i}
                    style={{
                      marginTop: i > 0 ? 16 : 0,
                      opacity: vpProgress,
                      transform: `translateY(${interpolate(vpProgress, [0, 1], [14, 0])}px)`,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                      <span
                        style={{
                          fontFamily: FONTS.sans,
                          fontSize: 12,
                          fontWeight: 600,
                          color: stanceColor,
                          backgroundColor: stanceColor + "12",
                          borderRadius: 10,
                          padding: "3px 12px",
                          whiteSpace: "nowrap",
                          flexShrink: 0,
                          letterSpacing: 0.3,
                        }}
                      >
                        {stance}
                      </span>
                      <span
                        style={{
                          fontFamily: FONTS.sans,
                          fontSize: 20,
                          color: COLORS.text,
                          lineHeight: 1.45,
                          fontWeight: 500,
                        }}
                      >
                        {summary}
                      </span>
                    </div>
                    {(() => {
                      if (!quote_cn && !quote) return null;
                      const stripHtml = (s: string) =>
                        s.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
                      const quoteCnDisplay = quote_cn
                        ? (() => {
                            const s = stripHtml(quote_cn);
                            return s.length > 100 ? s.slice(0, 100) + "…" : s;
                          })()
                        : null;
                      return (
                        <div style={{ marginTop: 6, marginLeft: 6, lineHeight: 1.4 }}>
                          {quoteCnDisplay && (
                            <div
                              style={{
                                fontFamily: FONTS.sans,
                                fontSize: 16,
                                color: COLORS.dim,
                                fontStyle: "italic",
                              }}
                            >
                              "{quoteCnDisplay}"
                            </div>
                          )}
                          {quote && (
                            <div
                              style={{
                                fontFamily: FONTS.sans,
                                fontSize: 14,
                                color: COLORS.textLight,
                                fontStyle: "italic",
                                marginTop: quoteCnDisplay ? 4 : 0,
                              }}
                            >
                              "{quote}"
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                );
              })}
            </div>

            {hasPie && <StancePie distribution={stanceDistribution!} size={150} />}
          </div>
        </>
      )}
    </div>
  );
};
