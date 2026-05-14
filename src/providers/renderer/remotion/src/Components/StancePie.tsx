import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { COLORS, FONTS, FW } from "./design";

export const STANCE_COLORS: Record<string, string> = {
  支持: "#34C759",
  质疑: COLORS.orangeRed,
  中立: "#8E8E93",
  调侃: "#FFD60A",
  担忧: "#BF5AF2",
};

/** Donut chart with outside labels. `size` is the total rendering area including labels. */
export const StancePie: React.FC<{
  distribution: Record<string, number>;
  size: number;
  centerLabel?: string;
}> = ({ distribution, size, centerLabel }) => {
  const frame = useCurrentFrame();
  const cx = size / 2;
  const cy = size / 2;
  const labelPad = 22;
  const outerR = size / 2 - labelPad;
  const innerR = outerR * 0.55;
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);

  const pieProgress = interpolate(frame, [8, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  let cumulative = 0;
  const arcs = entries.map(([label, value], idx) => {
    const startAngle = cumulative * 2 * Math.PI;
    cumulative += value;
    const endAngle = cumulative * 2 * Math.PI;

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

    const midAngle = startAngle + (endAngle - startAngle) / 2 - Math.PI / 2;
    const labelR = outerR + 14;
    const labelX = cx + labelR * Math.cos(midAngle);
    const labelY = cy + labelR * Math.sin(midAngle);
    const onRight = Math.cos(midAngle) > -0.05;

    const showLabel = value > 0.08;
    const pct = Math.round(value * 100);

    return { label, value, path, color, labelX, labelY, showLabel, pct, idx, onRight };
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
          {arcs.map((arc) => (
            <path
              key={arc.idx}
              d={arc.path}
              fill={arc.color}
              stroke="rgba(13,13,15,0.6)"
              strokeWidth={1.5}
            />
          ))}
          {arcs.map((arc) => {
            if (!arc.showLabel) return null;
            return (
              <g key={`label-${arc.idx}`}>
                <text
                  x={arc.labelX}
                  y={arc.labelY - 6}
                  textAnchor={arc.onRight ? "start" : "end"}
                  dominantBaseline="auto"
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: 14,
                    fontWeight: FW.heavy,
                    fill: COLORS.text,
                    pointerEvents: "none",
                  }}
                >
                  {arc.pct}%
                </text>
                <text
                  x={arc.labelX}
                  y={arc.labelY + 10}
                  textAnchor={arc.onRight ? "start" : "end"}
                  dominantBaseline="auto"
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 12,
                    fontWeight: FW.bold,
                    fill: COLORS.textSecondary,
                    pointerEvents: "none",
                  }}
                >
                  {arc.label}
                </text>
              </g>
            );
          })}
        </svg>
        {centerLabel && (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              fontFamily: FONTS.mono,
              fontSize: 24,
              fontWeight: FW.heavy,
              color: COLORS.text,
              textAlign: "center",
              lineHeight: 1.2,
              pointerEvents: "none",
            }}
          >
            {centerLabel}
          </div>
        )}
      </div>
      {/* Inline legend with colored dots */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "4px 14px",
          marginTop: 12,
          justifyContent: "center",
        }}
      >
        {entries.map(([label, value]) => {
          const color = STANCE_COLORS[label] || COLORS.textSecondary;
          const pct = Math.round(value * 100);
          return (
            <span
              key={label}
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                fontWeight: FW.medium,
                color: COLORS.textSecondary,
                display: "flex",
                alignItems: "center",
                gap: 5,
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
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
