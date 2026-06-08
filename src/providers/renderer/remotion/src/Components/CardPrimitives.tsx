import React from "react";

import {
  CARD_LAYOUT,
  COLORS,
  COMMON_LAYOUT,
  EVENT_LAYOUT,
  FONTS,
  FW,
  GRADIENTS,
  SHADOWS,
  SURFACES,
  useDesign,
} from "./design";

type StyleProp = React.CSSProperties | undefined;

export const CardDivider: React.FC<{
  opacity?: number;
  style?: StyleProp;
}> = ({ opacity, style }) => {
  const d = useDesign();

  return (
    <div
      style={{
        width: "100%",
        maxWidth: d.scaled(CARD_LAYOUT.divider.maxWidth),
        height: d.scaled(CARD_LAYOUT.divider.height),
        borderRadius: d.scaled(CARD_LAYOUT.divider.borderRadius),
        background: GRADIENTS.accentSoft,
        opacity,
        ...style,
      }}
    />
  );
};

export const MetricPill: React.FC<{
  children: React.ReactNode;
  background?: string;
  color?: string;
  fontSize?: number;
  style?: StyleProp;
}> = ({ children, background = COLORS.surface2, color = COLORS.fg, fontSize, style }) => {
  const d = useDesign();

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: d.scaled(COMMON_LAYOUT.metricGap),
        fontFamily: FONTS.mono,
        fontSize: fontSize ?? d.fs.textSm,
        fontWeight: FW.bold,
        padding: `${d.scaled(COMMON_LAYOUT.metricPaddingY)}px ${d.scaled(COMMON_LAYOUT.metricPaddingX)}px`,
        borderRadius: d.scaled(COMMON_LAYOUT.pillRadius),
        background,
        color,
        fontVariantNumeric: "tabular-nums",
        ...style,
      }}
    >
      {children}
    </span>
  );
};

export const KeywordTag: React.FC<{
  children: React.ReactNode;
  maxWidth?: number;
  style?: StyleProp;
}> = ({ children, maxWidth, style }) => {
  const d = useDesign();

  return (
    <span
      style={{
        display: "inline-block",
        fontFamily: FONTS.sans,
        fontSize: d.fs.textSm,
        fontWeight: FW.semibold,
        padding: `${d.scaled(EVENT_LAYOUT.tagPaddingY)}px ${d.scaled(EVENT_LAYOUT.tagPaddingX)}px`,
        borderRadius: d.scaled(COMMON_LAYOUT.pillRadius),
        border: `1px solid ${COLORS.border}`,
        background: SURFACES.tag,
        color: COLORS.muted,
        maxWidth: maxWidth ? d.scaled(maxWidth) : undefined,
        minHeight: d.scaled(45),
        whiteSpace: "normal",
        lineHeight: 1.25,
        ...style,
      }}
    >
      {children}
    </span>
  );
};

export const SectionHeading: React.FC<{
  children: React.ReactNode;
  color?: string;
  markerColor?: string;
  style?: StyleProp;
}> = ({ children, color = COLORS.brandDeep, markerColor = COLORS.brand, style }) => {
  const d = useDesign();

  return (
    <span
      style={{
        display: "flex",
        alignItems: "center",
        gap: d.scaled(COMMON_LAYOUT.itemGap - COMMON_LAYOUT.smallRadius),
        color,
        fontSize: d.fs.textXl,
        fontWeight: FW.heavy,
        ...style,
      }}
    >
      <span
        style={{
          width: d.scaled(COMMON_LAYOUT.sectionMarkerWidth),
          height: d.scaled(COMMON_LAYOUT.sectionMarkerHeight),
          borderRadius: d.scaled(COMMON_LAYOUT.pillRadius),
          background: markerColor,
          flexShrink: 0,
        }}
      />
      {children}
    </span>
  );
};

export const Panel: React.FC<{
  children: React.ReactNode;
  minHeight?: number;
  style?: StyleProp;
}> = ({ children, minHeight, style }) => {
  const d = useDesign();

  return (
    <div
      style={{
        border: `1px solid ${COLORS.border}`,
        borderRadius: d.scaled(COMMON_LAYOUT.panelRadius),
        background: SURFACES.panel,
        boxShadow: SHADOWS.panel,
        padding: `${d.scaled(COMMON_LAYOUT.panelPaddingY)}px ${d.scaled(COMMON_LAYOUT.panelPaddingX)}px`,
        display: "flex",
        flexDirection: "column",
        gap: d.scaled(COMMON_LAYOUT.panelGap),
        minHeight: minHeight ? d.scaled(minHeight) : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const NumberDisc: React.FC<{
  children: React.ReactNode;
  variant?: "solid" | "soft";
  size?: number;
  style?: StyleProp;
}> = ({ children, variant = "soft", size = COMMON_LAYOUT.numDiscSize, style }) => {
  const d = useDesign();
  const solid = variant === "solid";

  return (
    <span
      style={{
        width: d.scaled(size),
        height: d.scaled(size),
        borderRadius: COMMON_LAYOUT.circleRadius,
        background: solid ? COLORS.brand : COLORS.brandSoft,
        color: solid ? COLORS.white : COLORS.brandDeep,
        fontFamily: FONTS.serif,
        fontSize: d.fs.textLg,
        fontWeight: FW.heavy,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        boxShadow: solid ? SHADOWS.brandBadge : "none",
        ...style,
      }}
    >
      {children}
    </span>
  );
};

export const SlideIndicator: React.FC<{
  current: number;
  total: number;
  style?: StyleProp;
}> = ({ current, total, style }) => {
  const d = useDesign();

  if (!total) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: d.scaled(CARD_LAYOUT.padding.top),
        right: d.scaled(CARD_LAYOUT.padding.right),
        padding: `${d.scaled(6)}px ${d.scaled(18)}px`,
        borderRadius: d.scaled(COMMON_LAYOUT.pillRadius),
        background: "rgba(32,25,20,0.66)",
        color: COLORS.white,
        fontFamily: FONTS.mono,
        fontSize: d.fs.textSm,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "0.04em",
        zIndex: 12,
        ...style,
      }}
    >
      {current} / {total}
    </div>
  );
};
