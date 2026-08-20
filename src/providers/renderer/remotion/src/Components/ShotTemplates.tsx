import React from "react";
import { staticFile, useCurrentFrame } from "remotion";

import { CardShell } from "./CardShell";
import { MetricPill, NumberDisc, Panel, SectionHeading } from "./CardPrimitives";
import { COLORS, FONTS, FW, SURFACES, useDesign } from "./design";
import { ANIM_PRESETS, fadeUp } from "./timing";
import type { ElementProps } from "./utils";

type UnknownRecord = Record<string, unknown>;

const stringProp = (props: UnknownRecord, key: string, fallback = ""): string => {
  const value = props[key];
  if (value === undefined || value === null) return fallback;
  return typeof value === "string" ? value : String(value);
};

const stringListProp = (props: UnknownRecord, key: string): string[] => {
  const value = props[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
};

const recordListProp = (props: UnknownRecord, key: string): UnknownRecord[] => {
  const value = props[key];
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is UnknownRecord =>
      Boolean(item) && typeof item === "object" && !Array.isArray(item),
  );
};

const shortSource = (value: string): string => {
  if (!value) return "";
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value.length > 48 ? `${value.slice(0, 45)}...` : value;
  }
};

const assetSource = (value: string): string => {
  if (!value) return "";
  return /^(https?:)?\/\//.test(value) ? value : staticFile(value);
};

const TemplateFooter: React.FC<{ source?: string; label?: string }> = ({
  source,
  label = "HN DAILY",
}) => {
  const d = useDesign();
  if (!source && !label) return null;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: d.scaled(18),
        color: COLORS.muted,
        fontFamily: FONTS.mono,
        fontSize: d.fs.textXs,
        letterSpacing: "0.04em",
      }}
    >
      <span>{label}</span>
      {source && (
        <span style={{ maxWidth: "62%", overflow: "hidden", textOverflow: "ellipsis" }}>
          {source}
        </span>
      )}
    </div>
  );
};

/** Large editorial hook for a headline or a section opener. */
export const HeadlineShot: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const d = useDesign();
  const frame = useCurrentFrame();
  const props = elementProps as UnknownRecord;
  const eyebrow = stringProp(props, "section_label", stringProp(props, "eyebrow", "HEADLINE"));
  const title = stringProp(props, "title", stringProp(props, "headline", ""));
  const subtitle = stringProp(props, "subtitle", stringProp(props, "dek", ""));
  const stat = stringProp(props, "stat");
  const statLabel = stringProp(props, "stat_label");
  const imageUrl = assetSource(stringProp(props, "image_src", stringProp(props, "image_url", "")));

  return (
    <CardShell
      elementProps={elementProps}
      justify="between"
      reserveSubtitle
      showTopBar
      showWaveform
    >
      <div style={fadeUp(frame, ANIM_PRESETS.title)}>
        <SectionHeading>{eyebrow}</SectionHeading>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: d.scaled(28), maxWidth: "92%" }}>
        <h1
          style={{
            margin: 0,
            color: COLORS.brandDeep,
            fontFamily: FONTS.serifBold,
            fontSize: d.fs.text6xl,
            fontWeight: FW.heavy,
            lineHeight: 1.08,
            letterSpacing: "-0.025em",
            ...fadeUp(frame, ANIM_PRESETS.body),
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            style={{
              margin: 0,
              color: COLORS.textBody,
              fontFamily: FONTS.sans,
              fontSize: d.fs.text2xl,
              fontWeight: FW.medium,
              lineHeight: 1.45,
              maxWidth: d.scaled(1040),
              ...fadeUp(frame, ANIM_PRESETS.meta),
            }}
          >
            {subtitle}
          </p>
        )}
        {stat && (
          <div style={fadeUp(frame, ANIM_PRESETS.meta, 3)}>
            <MetricPill
              background={COLORS.brandSoft}
              color={COLORS.brandDeep}
              fontSize={d.fs.textBase}
            >
              {statLabel ? `${stat} · ${statLabel}` : stat}
            </MetricPill>
          </div>
        )}
        {imageUrl && (
          <Panel
            style={{
              minHeight: d.scaled(220),
              maxHeight: d.scaled(300),
              overflow: "hidden",
              padding: 0,
              ...fadeUp(frame, ANIM_PRESETS.meta, 5),
            }}
          >
            <img src={imageUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
          </Panel>
        )}
      </div>
      <TemplateFooter source={stringProp(props, "source_label")} />
    </CardShell>
  );
};

/** Evidence-first layout for an article, HN thread, screenshot, or document. */
export const SourceEvidenceShot: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const d = useDesign();
  const frame = useCurrentFrame();
  const props = elementProps as UnknownRecord;
  const eyebrow = stringProp(props, "section_label", stringProp(props, "eyebrow", "EVIDENCE"));
  const title = stringProp(props, "title", "来源与证据");
  const caption = stringProp(props, "caption", stringProp(props, "summary", ""));
  const imageUrl = assetSource(stringProp(props, "image_url", stringProp(props, "image_src", "")));
  const sourceUrl = stringProp(props, "source_url");
  const highlights = stringListProp(props, "highlights").slice(0, 4);

  return (
    <CardShell elementProps={elementProps} justify="start" reserveSubtitle showTopBar showWaveform>
      <div style={fadeUp(frame, ANIM_PRESETS.title)}>
        <SectionHeading>{eyebrow}</SectionHeading>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: imageUrl ? "1.15fr 0.85fr" : "1fr",
          gap: d.scaled(30),
          flex: 1,
          minHeight: 0,
          ...fadeUp(frame, ANIM_PRESETS.body),
        }}
      >
        <Panel style={{ minHeight: d.scaled(390), overflow: "hidden", padding: 0 }}>
          {imageUrl ? (
            <img
              src={imageUrl}
              alt=""
              style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
            />
          ) : (
            <div
              style={{
                height: "100%",
                minHeight: d.scaled(390),
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: d.scaled(42),
                color: COLORS.muted,
                fontFamily: FONTS.mono,
                fontSize: d.fs.textBase,
                textAlign: "center",
              }}
            >
              {sourceUrl ? shortSource(sourceUrl) : "SOURCE IMAGE"}
            </div>
          )}
        </Panel>
        <div style={{ display: "flex", flexDirection: "column", gap: d.scaled(24), minWidth: 0 }}>
          <h1
            style={{
              margin: 0,
              color: COLORS.brandDeep,
              fontFamily: FONTS.serifBold,
              fontSize: d.fs.text4xl,
              lineHeight: 1.12,
              fontWeight: FW.heavy,
            }}
          >
            {title}
          </h1>
          {caption && (
            <p
              style={{
                margin: 0,
                color: COLORS.textBody,
                fontFamily: FONTS.sans,
                fontSize: d.fs.textLg,
                lineHeight: 1.45,
              }}
            >
              {caption}
            </p>
          )}
          {highlights.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: d.scaled(16) }}>
              {highlights.map((item, index) => (
                <div
                  key={`${item}-${index}`}
                  style={{ display: "flex", gap: d.scaled(14), alignItems: "flex-start" }}
                >
                  <span
                    style={{
                      color: COLORS.brand,
                      fontFamily: FONTS.mono,
                      fontSize: d.fs.textSm,
                      fontWeight: FW.bold,
                      paddingTop: d.scaled(4),
                    }}
                  >
                    0{index + 1}
                  </span>
                  <span
                    style={{
                      color: COLORS.textBody,
                      fontFamily: FONTS.sans,
                      fontSize: d.fs.textBase,
                      lineHeight: 1.35,
                    }}
                  >
                    {item}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <TemplateFooter source={shortSource(sourceUrl)} label="SOURCE / HN DAILY" />
    </CardShell>
  );
};

/** One community viewpoint, intended for a short HN comment beat. */
export const CommentShot: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const d = useDesign();
  const frame = useCurrentFrame();
  const props = elementProps as UnknownRecord;
  const sectionLabel = stringProp(props, "section_label");
  const eyebrow = stringProp(
    props,
    "eyebrow",
    sectionLabel ? `HN 评论 · ${sectionLabel}` : "HN COMMENT",
  );
  const quote = stringProp(props, "quote", stringProp(props, "comment_summary", ""));
  const author = stringProp(props, "author", "HN community");
  const stance = stringProp(props, "stance", "观点");
  const sourceUrl = stringProp(props, "source_url");

  return (
    <CardShell
      elementProps={elementProps}
      justify="between"
      reserveSubtitle
      showTopBar
      showWaveform
    >
      <div style={fadeUp(frame, ANIM_PRESETS.title)}>
        <SectionHeading markerColor={COLORS.brand}>{eyebrow}</SectionHeading>
      </div>
      <Panel
        style={{
          background: SURFACES.panel,
          padding: d.scaled(42),
          ...fadeUp(frame, ANIM_PRESETS.body),
        }}
      >
        <div
          style={{
            color: COLORS.brand,
            fontFamily: FONTS.serif,
            fontSize: d.fs.text6xl,
            lineHeight: 0.75,
            height: d.scaled(42),
          }}
        >
          “
        </div>
        <p
          style={{
            margin: 0,
            color: COLORS.textBody,
            fontFamily: FONTS.serif,
            fontSize: d.fs.text3xl,
            lineHeight: 1.35,
            fontWeight: FW.medium,
          }}
        >
          {quote}
        </p>
        <div
          style={{
            marginTop: d.scaled(28),
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: d.scaled(18),
            color: COLORS.muted,
            fontFamily: FONTS.mono,
            fontSize: d.fs.textSm,
          }}
        >
          <span>{author}</span>
          <MetricPill>{stance}</MetricPill>
        </div>
      </Panel>
      <TemplateFooter source={shortSource(sourceUrl)} label="HN COMMENT · COMMUNITY VIEW" />
    </CardShell>
  );
};

/** Two-sided community debate without forcing a single editorial conclusion. */
export const CommentDualShot: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const d = useDesign();
  const frame = useCurrentFrame();
  const props = elementProps as UnknownRecord;
  const left = stringProp(props, "left_summary", stringProp(props, "left_text", ""));
  const right = stringProp(props, "right_summary", stringProp(props, "right_text", ""));
  const leftLabel = stringProp(props, "left_label", "观点 A");
  const rightLabel = stringProp(props, "right_label", "观点 B");
  const sectionLabel = stringProp(props, "section_label");
  const title = stringProp(
    props,
    "title",
    sectionLabel ? `HN 评论 · ${sectionLabel}` : "评论区的分歧",
  );
  const note = stringProp(props, "note", "");

  const debatePanel = (label: string, text: string, color: string, delay: number) => (
    <Panel
      style={{
        flex: 1,
        minWidth: 0,
        borderTop: `${d.scaled(6)}px solid ${color}`,
        ...fadeUp(frame, ANIM_PRESETS.body, delay),
      }}
    >
      <div
        style={{
          color,
          fontFamily: FONTS.mono,
          fontSize: d.fs.textSm,
          fontWeight: FW.bold,
          letterSpacing: "0.04em",
        }}
      >
        {label}
      </div>
      <p
        style={{
          margin: 0,
          color: COLORS.textBody,
          fontFamily: FONTS.sans,
          fontSize: d.fs.text2xl,
          lineHeight: 1.4,
        }}
      >
        {text}
      </p>
    </Panel>
  );

  return (
    <CardShell elementProps={elementProps} justify="start" reserveSubtitle showTopBar showWaveform>
      <div style={fadeUp(frame, ANIM_PRESETS.title)}>
        <SectionHeading>{title}</SectionHeading>
      </div>
      <div
        style={{ display: "flex", gap: d.scaled(24), flex: 1, minHeight: 0, alignItems: "stretch" }}
      >
        {debatePanel(leftLabel, left, COLORS.brand, 0)}
        {debatePanel(rightLabel, right, COLORS.sage, 3)}
      </div>
      {note && (
        <p
          style={{
            margin: 0,
            color: COLORS.muted,
            fontFamily: FONTS.sans,
            fontSize: d.fs.textLg,
            lineHeight: 1.35,
            ...fadeUp(frame, ANIM_PRESETS.meta),
          }}
        >
          {note}
        </p>
      )}
      <TemplateFooter label="HN COMMENT · TWO VIEWS" />
    </CardShell>
  );
};

/** One concrete number with optional comparison rows. */
export const DataNumberShot: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const d = useDesign();
  const frame = useCurrentFrame();
  const props = elementProps as UnknownRecord;
  const sectionLabel = stringProp(props, "section_label");
  const value = stringProp(props, "value", stringProp(props, "number", "0"));
  const label = stringProp(props, "label", "数据点");
  const context = stringProp(props, "context", "");
  const sourceUrl = stringProp(props, "source_url");
  const comparisons = recordListProp(props, "comparisons").slice(0, 4);
  const imageUrl = assetSource(stringProp(props, "image_src", stringProp(props, "image_url", "")));

  return (
    <CardShell
      elementProps={elementProps}
      justify="between"
      reserveSubtitle
      showTopBar
      showWaveform
    >
      <div style={fadeUp(frame, ANIM_PRESETS.title)}>
        <SectionHeading>{sectionLabel || "DATA POINT"}</SectionHeading>
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: d.scaled(16),
          ...fadeUp(frame, ANIM_PRESETS.body),
        }}
      >
        <div
          style={{ display: "flex", alignItems: "baseline", gap: d.scaled(20), flexWrap: "wrap" }}
        >
          <span
            style={{
              color: COLORS.brandDeep,
              fontFamily: FONTS.serifBold,
              fontSize: d.fs.text6xl,
              fontWeight: FW.heavy,
              lineHeight: 1,
            }}
          >
            {value}
          </span>
          <span
            style={{
              color: COLORS.textBody,
              fontFamily: FONTS.sans,
              fontSize: d.fs.text3xl,
              fontWeight: FW.bold,
            }}
          >
            {label}
          </span>
        </div>
        {context && (
          <p
            style={{
              margin: 0,
              color: COLORS.muted,
              fontFamily: FONTS.sans,
              fontSize: d.fs.textXl,
              lineHeight: 1.4,
            }}
          >
            {context}
          </p>
        )}
        {imageUrl && (
          <Panel
            style={{
              minHeight: d.scaled(200),
              maxHeight: d.scaled(280),
              overflow: "hidden",
              padding: 0,
              ...fadeUp(frame, ANIM_PRESETS.meta, 3),
            }}
          >
            <img src={imageUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
          </Panel>
        )}
      </div>
      {comparisons.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: d.scaled(14),
            ...fadeUp(frame, ANIM_PRESETS.meta),
          }}
        >
          {comparisons.map((item, index) => {
            const itemLabel = stringProp(item, "label", `比较项 ${index + 1}`);
            const itemValue = stringProp(item, "value", "");
            return (
              <div
                key={`${itemLabel}-${index}`}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: d.scaled(20),
                  borderBottom: `1px solid ${COLORS.border}`,
                  paddingBottom: d.scaled(12),
                }}
              >
                <span
                  style={{
                    color: COLORS.textBody,
                    fontFamily: FONTS.sans,
                    fontSize: d.fs.textBase,
                  }}
                >
                  {itemLabel}
                </span>
                <span
                  style={{
                    color: COLORS.brandDeep,
                    fontFamily: FONTS.mono,
                    fontSize: d.fs.textBase,
                    fontWeight: FW.bold,
                  }}
                >
                  {itemValue}
                </span>
              </div>
            );
          })}
        </div>
      )}
      <TemplateFooter source={shortSource(sourceUrl)} label="HN DAILY · DATA" />
    </CardShell>
  );
};

/** Dense but readable one-fact layout for the quick-news layer. */
export const QuickNewsShot: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const d = useDesign();
  const frame = useCurrentFrame();
  const props = elementProps as UnknownRecord;
  const index = stringProp(props, "index", stringProp(props, "display_index", ""));
  const title = stringProp(props, "title", stringProp(props, "headline", "").trim());
  const fact = stringProp(props, "fact", stringProp(props, "summary", ""));
  const commentFocus = stringProp(props, "comment_focus", "");
  const sourceUrl = stringProp(props, "source_url");
  const imageUrl = assetSource(stringProp(props, "image_src", stringProp(props, "image_url", "")));
  const sectionLabel = stringProp(props, "section_label", "速览");

  return (
    <CardShell
      elementProps={elementProps}
      justify="between"
      reserveSubtitle
      showTopBar
      showWaveform={false}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          ...fadeUp(frame, ANIM_PRESETS.title),
        }}
      >
        <SectionHeading>{sectionLabel}</SectionHeading>
        {index && <MetricPill>{index}</MetricPill>}
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: d.scaled(24),
          ...fadeUp(frame, ANIM_PRESETS.body),
        }}
      >
        <h1
          style={{
            margin: 0,
            color: COLORS.brandDeep,
            fontFamily: FONTS.serifBold,
            fontSize: d.fs.text4xl,
            lineHeight: 1.15,
            fontWeight: FW.heavy,
          }}
        >
          {title}
        </h1>
        <p
          style={{
            margin: 0,
            color: COLORS.textBody,
            fontFamily: FONTS.sans,
            fontSize: d.fs.text2xl,
            lineHeight: 1.42,
          }}
        >
          {fact}
        </p>
        {imageUrl && (
          <Panel
            style={{
              minHeight: d.scaled(190),
              maxHeight: d.scaled(260),
              overflow: "hidden",
              padding: 0,
              ...fadeUp(frame, ANIM_PRESETS.meta, 2),
            }}
          >
            <img src={imageUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
          </Panel>
        )}
        {commentFocus && (
          <Panel
            style={{
              background: COLORS.brandBg,
              borderColor: COLORS.brandBorder,
              ...fadeUp(frame, ANIM_PRESETS.meta),
            }}
          >
            <div
              style={{
                color: COLORS.brandDeep,
                fontFamily: FONTS.mono,
                fontSize: d.fs.textXs,
                fontWeight: FW.bold,
              }}
            >
              HN PULSE
            </div>
            <div
              style={{
                color: COLORS.textBody,
                fontFamily: FONTS.sans,
                fontSize: d.fs.textBase,
                lineHeight: 1.35,
              }}
            >
              {commentFocus}
            </div>
          </Panel>
        )}
      </div>
      <TemplateFooter source={shortSource(sourceUrl)} label="HN DAILY · QUICK" />
    </CardShell>
  );
};

/** Three concise signals for the closing beat. */
export const SignalsShot: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const d = useDesign();
  const frame = useCurrentFrame();
  const props = elementProps as UnknownRecord;
  const title = stringProp(props, "title", "TODAY'S SIGNALS");
  const rawItems = stringListProp(props, "items");
  const items = (rawItems.length > 0 ? rawItems : stringListProp(props, "takeaways")).slice(0, 3);

  return (
    <CardShell
      elementProps={elementProps}
      justify="between"
      reserveSubtitle
      showTopBar={false}
      showWaveform={false}
    >
      <div style={fadeUp(frame, ANIM_PRESETS.title)}>
        <SectionHeading>{title}</SectionHeading>
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: d.scaled(22),
          ...fadeUp(frame, ANIM_PRESETS.body),
        }}
      >
        {items.map((item, index) => (
          <div
            key={`${item}-${index}`}
            style={{ display: "flex", gap: d.scaled(18), alignItems: "flex-start" }}
          >
            <NumberDisc variant={index === 0 ? "solid" : "soft"}>{index + 1}</NumberDisc>
            <p
              style={{
                margin: d.scaled(6),
                color: COLORS.textBody,
                fontFamily: FONTS.sans,
                fontSize: d.fs.text2xl,
                lineHeight: 1.35,
                fontWeight: FW.medium,
              }}
            >
              {item}
            </p>
          </div>
        ))}
      </div>
      <TemplateFooter label="HN DAILY · END" />
    </CardShell>
  );
};

export const ShotTemplatePrimitives = {
  HeadlineShot,
  SourceEvidenceShot,
  CommentShot,
  CommentDualShot,
  DataNumberShot,
  QuickNewsShot,
  SignalsShot,
};
