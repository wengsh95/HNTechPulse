import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { COLORS, FONTS, FW } from "./design";

export const STANCE_COLORS: Record<string, string> = {
  支持: "#34C759",
  质疑: "#FF453A",
  中立: "rgba(245,245,247,0.50)",
  调侃: "#FFD60A",
  担忧: "#BF5AF2",
};

export const StancePie: React.FC<{
  distribution: Record<string, number>;
  size: number;
  centerLabel?: string;
}> = ({ distribution, size, centerLabel }) => {
  const frame = useCurrentFrame();
  const cx = size / 2;
  const cy = size / 2;
  const outerR = size / 2 - 6;
  const innerR = outerR * 0.68;
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);

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

    // Arc reveal: each arc sweeps from its startAngle to a progressively revealed endAngle
    const revealedEndAngle = startAngle + (endAngle - startAngle) * pieProgress;
    const largeArc = revealedEndAngle - startAngle > Math.PI ? 1 : 0;

    const outerX1 = cx + outerR * Math.cos(startAngle - Math.PI / 2);
    const outerY1 = cy + outerR * Math.sin(startAngle - Math.PI / 2);
    const outerX2 = cx + outerR * Math.cos(revealedEndAngle - Math.PI / 2);
    const outerY2 = cy + outerR * Math.sin(revealedEndAngle - Math.PI / 2);
    const innerX1 = cx + innerR * Math.cos(startAngle - Math.PI / 2);
    const innerY1 = cy + innerR * Math.sin(startAngle - Math.PI / 2);
    const innerX2 = cx + innerR * Math.cos(revealedEndAngle - Math.PI / 2);
    const innerY2 = cy + innerR * Math.sin(revealedEndAngle - Math.PI / 2);

    const path = `M ${outerX1} ${outerY1} A ${outerR} ${outerR} 0 ${largeArc} 1 ${outerX2} ${outerY2} L ${innerX2} ${innerY2} A ${innerR} ${innerR} 0 ${largeArc} 0 ${innerX1} ${innerY1} Z`;
    const color = STANCE_COLORS[label] || COLORS.textSecondary;
    return { label, value, path, color };
  });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        flexShrink: 0,
      }}
    >
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {arcs.map((arc, i) => (
            <path
              key={i}
              d={arc.path}
              fill={arc.color}
              stroke="rgba(13,13,15,0.5)"
              strokeWidth={1}
            />
          ))}
        </svg>
        {centerLabel && (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              fontFamily: FONTS.mono,
              fontSize: 18,
              fontWeight: FW.bold,
              color: COLORS.text,
              textAlign: "center",
              lineHeight: 1.25,
              pointerEvents: "none",
            }}
          >
            {centerLabel}
          </div>
        )}
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "6px 14px",
          marginTop: 12,
          justifyContent: "center",
        }}
      >
        {entries.map(([label, value], i) => {
          const color = STANCE_COLORS[label] || COLORS.textSecondary;
          const legendDelay = 30 + i * 5;
          const legendProgress = interpolate(frame, [legendDelay, legendDelay + 14], [0, 1], {
            easing: Easing.bezier(0.16, 1, 0.3, 1),
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <span
              key={label}
              style={{
                fontFamily: FONTS.sans,
                fontSize: 13,
                fontWeight: FW.medium,
                color: COLORS.text,
                display: "flex",
                alignItems: "center",
                gap: 6,
                opacity: legendProgress,
                transform: `translateY(${interpolate(legendProgress, [0, 1], [6, 0])}px)`,
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
