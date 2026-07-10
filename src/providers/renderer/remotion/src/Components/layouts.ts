import { COLORS, COMMON_LAYOUT, CARD_REF } from "./tokens";

export const CARD_LAYOUT = {
  padding: {
    top: 63,
    bottom: 168,
    left: 69,
    right: 69,
  },

  header: {
    height: 48,
    marginBottom: 16,
    fontSize: 18,
    color: COLORS.dim,
  },

  watermark: {
    top: 64,
    right: 70,
    fontSize: 113,
  },

  waveform: {
    bottom: 20,
  },

  divider: {
    height: 2,
    maxWidth: 1560,
    borderRadius: 1,
  },

  content: {
    maxWidth: 1560,
    wideMaxWidth: 1782,
  },

  shell: {
    radius: 27,
    topBarTop: 63,
    dividerBottom: 117,
    headerSlotTop: 63,
    headerContentTop: 30,
    subtitleReserve: 292,
    contentGap: 36,
    footerTop: 30,
    brandGap: 12,
    dateGap: 18,
    liveDotSize: 14,
  },
} as const;

export const COVER_LAYOUT = {
  gutter: CARD_LAYOUT.padding.left,
  paddingTop: CARD_LAYOUT.padding.top,
  paddingBottom: CARD_LAYOUT.padding.bottom,
  fillGap: 36,
  rowGap: 24,
  rowPaddingY: 24,
  rowStagger: 6,
  rankBadgeSize: COMMON_LAYOUT.numDiscSize,
  titleGap: 24,
  originalGap: 6,
  headlineMaxWidth: 1560,
  deckMaxWidth: 1350,
  dividerMaxWidth: 1200,
  dividerHeight: 6,
  dividerRadius: 3,
  dotSize: 8,
  dotGap: 6,
  decorRightOffset: 20,
  decorTop: 140,
  decorWidth: 2,
  decorHeight: 300,
  decorRadius: 1,
  decorStart: 6,
  decorEnd: 24,
} as const;

export const EVENT_LAYOUT = {
  gutter: CARD_LAYOUT.padding.left,
  paddingTop: CARD_LAYOUT.padding.top,
  paddingBottom: CARD_LAYOUT.padding.bottom,
  badgeGap: 6,
  badgePaddingY: 6,
  badgePaddingX: 16,
  badgeRadius: 4,
  titleEnMarginTop: -12,
  titleEnMarginBottom: 2,
  headerGap: 16,
  statsGap: 12,
  heatPaddingX: 18,
  analysisGap: 12,
  analysisMaxWidth: 690,
  analysisItemGap: 24,
  analysisBarMinHeight: 56,
  tagGap: 8,
  tagPaddingY: 6,
  tagPaddingX: 18,
  tagMaxWidth: 360,
  imageWidth: 760,
  imageTextReserve: 0,
  imageTop: 0,
  imageBottom: 0,
  imageRadius: 21,
  imageMaskHeight: 120,
  logoWidth: 220,
  twoColumnGap: 36,
  textGap: 24,
  bodyColumnGap: 36,
  bodyRowGap: 24,
  metaMinHeight: 63,
  imageMinHeight: 405,
  titleMaxWidth: 1500,
  titleScale: 0.94,
  bodyMaxHeight: 445,
} as const;

export const ATMOSPHERE_LAYOUT = {
  gutter: CARD_LAYOUT.padding.left,
  paddingTop: CARD_LAYOUT.padding.top,
  paddingBottom: CARD_LAYOUT.padding.bottom,
  fillGap: 24,
  summaryMaxWidth: 1350,
  gridGap: 30,
  gridColumns: [0.9, 1.05, 1.05],
  panelMinHeight: 405,
  stanceRowGap: 8,
  stanceBarHeight: 17,
  focusGap: 18,
  quoteLimit: 3,
} as const;

export const BACKGROUND_LAYOUT = {
  width: CARD_REF.width,
  height: CARD_REF.height,
  dotGridSize: 40,
  glowBlur: 40,
  glowDriftAmplitude: 30,
  glowTransparentStop: 55,
} as const;

export const CARD_WAVEFORM_LAYOUT = {
  barCount: 56,
  barWidth: 10,
  barGap: 4,
  maxHeight: 44,
  leftOffset: 32,
} as const;

export const WAVEFORM_LAYOUT = {
  barCount: 28,
  barWidth: 6,
  barGap: 4,
  maxHeight: 80,
  bottomOffset: 20,
  fallbackMinHeight: 4,
  fallbackAmplitude: 0.2,
  simulatedMinAmplitude: 0.05,
  simulatedBaseAmplitude: 0.5,
  frameSpeed: 0.06,
  barPhaseStep: 0.35,
  opacityBase: 0.35,
  opacityScale: 0.25,
  canvasWidth: CARD_REF.width,
} as const;

export const AUDIO_ANALYSIS_LAYOUT = {
  silenceFloor: 1e-6,
  dbRange: 80,
  minVisualAmplitude: 0.02,
} as const;

export const CLOSING_LAYOUT = {
  gutter: CARD_LAYOUT.padding.left,
  paddingTop: CARD_LAYOUT.padding.top,
  paddingBottom: CARD_LAYOUT.padding.bottom,
  fillGap: 36,
  listGap: 24,
  rowGap: 24,
  subtitleMarginTop: 6,
  centerThreshold: 3,
  titleScale: 0.86,
} as const;

export const SUBTITLE_LAYOUT = {
  cueToleranceSeconds: 0,
  fadeOutSeconds: 0,
  fadeInSeconds: 0.06,
  bottomOffset: 8,
  paddingY: 11,
  paddingX: 30,
  minHeight: 62,
  opacity: 0.88,
  radius: 12,
  fontScale: 1,
  lineHeight: 1.18,
  maxLines: 1,
  enterSlideY: 6,
  exitSlideY: 4,
} as const;

export const PROGRESS_LAYOUT = {
  fadeInFrames: 12,
  barHeight: 3,
  tickHeight: 8,
  tickWidth: 1.5,
  tickRadius: 1,
  outerPaddingBottom: 8,
} as const;

export const COMPOSITION_LAYOUT = {
  fadeFrames: 4,
  transitionFrames: 12,
  chapterTitleMaxChars: 14,
  chapterTitleSliceChars: 13,
} as const;

export const TIMING_LAYOUT = {
  segmentFadeFrames: 4,
} as const;
