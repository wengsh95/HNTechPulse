import React from "react";
import { interpolate, staticFile, useCurrentFrame } from "remotion";

import type { AnalysisItem, EventCardProps, HeatLevel } from "./cardTypes";
import { CardShell } from "./CardShell";
import { KeywordTag, MetricPill, Panel, SectionHeading, SlideIndicator } from "./CardPrimitives";
import {
  ANIM,
  CARD_LAYOUT,
  COLORS,
  COMMON_LAYOUT,
  EASE_CARD,
  EVENT_LAYOUT,
  FONTS,
  FW,
  useDesign,
} from "./design";
import { extractEventProps } from "./propsExtractors";
import type { ElementProps } from "./utils";

const HEAT_LABELS: Record<HeatLevel, string> = {
  L1: "热度等级 L1",
  L2: "热度等级 L2",
  L3: "热度等级 L3",
};

const HEAT_COLORS: Record<HeatLevel, { bg: string; fg: string }> = {
  L1: { bg: COLORS.sageBg, fg: COLORS.sage },
  L2: { bg: COLORS.goldBg, fg: COLORS.yellow },
  L3: { bg: COLORS.brandSoft, fg: COLORS.brandDeep },
};

const ANALYSIS_META: Record<
  AnalysisItem["type"],
  { label: string; barColor: string; labelColor: string }
> = {
  why: { label: "为何关注", barColor: COLORS.brand, labelColor: COLORS.brandDeep },
  impact: { label: "影响分析", barColor: COLORS.brandLight, labelColor: COLORS.brandDeep },
};

function Header({ props, progress }: { props: EventCardProps; progress: number }) {
  const d = useDesign();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: d.scaled(10),
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [COMMON_LAYOUT.riseMedium, 0])}px)`,
      }}
    >
      <h1
        style={{
          margin: 0,
          maxWidth: d.scaled(EVENT_LAYOUT.titleMaxWidth),
          color: COLORS.fg,
          fontFamily: FONTS.serifBold,
          fontSize: Math.round(d.fs.text4xl * EVENT_LAYOUT.titleScale),
          fontWeight: FW.heavy,
          lineHeight: 1.14,
          letterSpacing: 0,
        }}
      >
        {props.title}
      </h1>
      {props.englishTitle && props.englishTitle !== props.title && (
        <p
          style={{
            margin: 0,
            maxWidth: d.scaled(CARD_LAYOUT.content.maxWidth),
            color: COLORS.inkSoft,
            fontFamily: FONTS.sans,
            fontSize: d.fs.textBase,
            lineHeight: 1.3,
          }}
        >
          {props.englishTitle}
        </p>
      )}
      {props.domain && (
        <small
          style={{
            display: "block",
            color: COLORS.muted,
            fontFamily: FONTS.mono,
            fontSize: d.fs.textSm,
            lineHeight: 1.3,
          }}
        >
          {props.domain}
        </small>
      )}
    </div>
  );
}

function MetaRow({ props, progress }: { props: EventCardProps; progress: number }) {
  const d = useDesign();

  return (
    <div
      style={{
        minHeight: d.scaled(EVENT_LAYOUT.metaMinHeight),
        paddingBottom: d.scaled(12),
        borderBottom: `1px solid ${COLORS.border}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: d.scaled(30),
        opacity: progress,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: d.scaled(12),
          flexWrap: "wrap",
          flex: "0 0 auto",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: `${d.scaled(COMMON_LAYOUT.metricPaddingY)}px ${d.scaled(27)}px`,
            borderRadius: d.scaled(COMMON_LAYOUT.pillRadius),
            background: HEAT_COLORS[props.heatLevel].bg,
            color: HEAT_COLORS[props.heatLevel].fg,
            fontFamily: FONTS.mono,
            fontSize: d.fs.textSm,
            fontWeight: FW.bold,
            fontVariantNumeric: "tabular-nums",
            letterSpacing: "0.04em",
          }}
        >
          {props.heatLabel || HEAT_LABELS[props.heatLevel]}
        </span>
        <MetricPill>hot {props.hnScore.toLocaleString()}</MetricPill>
        <MetricPill>com {props.commentCount.toLocaleString()}</MetricPill>
      </div>

      {props.keywords.length > 0 && (
        <div
          style={{
            minWidth: 0,
            display: "flex",
            justifyContent: "flex-end",
            flexWrap: "wrap",
            gap: d.scaled(12),
          }}
        >
          {props.keywords.map((kw) => (
            <KeywordTag key={kw}>{kw}</KeywordTag>
          ))}
        </div>
      )}
    </div>
  );
}

function AnalysisPanels({ items }: { items: AnalysisItem[] }) {
  const d = useDesign();
  const rendered = items.length > 0 ? items : [{ type: "why" as const, text: "暂无要点" }];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: d.scaled(18),
        minWidth: 0,
      }}
    >
      {rendered.slice(0, 2).map((item, i) => {
        const meta = ANALYSIS_META[item.type];
        return (
          <Panel key={`${item.type}-${i}`} style={{ flex: 1 }}>
            <SectionHeading color={meta.labelColor} markerColor={meta.barColor}>
              {meta.label}
            </SectionHeading>
            <p
              style={{
                margin: 0,
                color: COLORS.inkSoft,
                fontFamily: FONTS.sans,
                fontSize: d.fs.textBase,
                lineHeight: 1.45,
              }}
            >
              {item.text}
            </p>
          </Panel>
        );
      })}
    </div>
  );
}

export const EventCard: React.FC<ElementProps> = ({ elementProps }) => {
  const frame = useCurrentFrame();
  const d = useDesign();
  const props = extractEventProps(elementProps);
  const { imageUrl, logoUrl } = props;
  const hasVisual = Boolean(imageUrl || logoUrl);
  const isScreenshotLike =
    props.imageType === "screenshot" ||
    props.imageType === "document" ||
    Boolean(imageUrl?.toLowerCase().includes("screenshot"));

  const titleProgress = interpolate(frame, [ANIM.titleStart, ANIM.titleEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [ANIM.bodyStart, ANIM.bodyEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const visualProgress = interpolate(frame, [ANIM.imageStart, ANIM.imageEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <CardShell
      elementProps={elementProps}
      justify="start"
      gutter={EVENT_LAYOUT.gutter}
      paddingTop={EVENT_LAYOUT.paddingTop}
      paddingBottom={EVENT_LAYOUT.paddingBottom}
      showTopBar
      showWatermark={false}
      showWaveform
      reserveSubtitle
    >
      <SlideIndicator current={props.index} total={props.total} />

      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          gap: d.scaled(24),
        }}
      >
        <Header props={props} progress={titleProgress} />
        <MetaRow props={props} progress={bodyProgress} />

        <div
          style={{
            flex: 1,
            minHeight: 0,
            maxHeight: d.scaled(EVENT_LAYOUT.bodyMaxHeight),
            display: "grid",
            gridTemplateColumns: hasVisual ? "minmax(0, 0.92fr) minmax(0, 1.08fr)" : "1fr",
            gap: d.scaled(EVENT_LAYOUT.bodyColumnGap),
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [COMMON_LAYOUT.riseSmall, 0])}px)`,
          }}
        >
          <AnalysisPanels items={props.analysis} />

          {imageUrl && (
            <aside
              style={{
                minHeight: d.scaled(EVENT_LAYOUT.imageMinHeight),
                minWidth: 0,
                overflow: "hidden",
                border: `1px solid ${COLORS.border}`,
                borderRadius: d.scaled(COMMON_LAYOUT.panelRadius),
                background: COLORS.surface2,
                boxShadow: "0 10px 24px rgba(32,25,20,0.08)",
                opacity: visualProgress,
                transform: `translateX(${interpolate(visualProgress, [0, 1], [COMMON_LAYOUT.riseLarge, 0])}px)`,
              }}
            >
              <img
                src={staticFile(imageUrl)}
                alt=""
                style={{
                  width: "100%",
                  height: "100%",
                  display: "block",
                  objectFit: isScreenshotLike ? "contain" : "cover",
                  objectPosition: isScreenshotLike ? "top center" : "center",
                  background: isScreenshotLike ? COLORS.white : COLORS.surface2,
                }}
              />
            </aside>
          )}

          {logoUrl && !imageUrl && (
            <aside
              style={{
                minHeight: d.scaled(EVENT_LAYOUT.imageMinHeight),
                minWidth: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: `1px solid ${COLORS.border}`,
                borderRadius: d.scaled(COMMON_LAYOUT.panelRadius),
                background: COLORS.surface2,
                boxShadow: "0 10px 24px rgba(32,25,20,0.08)",
                opacity: visualProgress,
                transform: `translateX(${interpolate(visualProgress, [0, 1], [COMMON_LAYOUT.riseLarge, 0])}px)`,
              }}
            >
              <img
                src={staticFile(logoUrl)}
                alt="logo"
                style={{ width: d.scaled(330), objectFit: "contain" }}
              />
            </aside>
          )}
        </div>
      </div>
    </CardShell>
  );
};
