import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { COLORS, FONTS, FW } from "./design";

export const STANCE_COLORS: Record<string, string> = {
  "支持": "#3395ff",
  "质疑": "#ff4d4d",
  "中立": "#aeaeb2",
  "调侃": "#ffb340",
  "担忧": "#7d7aff",
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
        opacity: pieProgress,
      }}
    >
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {arcs.map((arc, i) => (
            <path
              key={i}
              d={arc.path}
              fill={arc.color}
              stroke="rgba(0,0,0,0.3)"
              strokeWidth={2}
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
        {entries.map(([label, value]) => {
          const color = STANCE_COLORS[label] || COLORS.textSecondary;
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
