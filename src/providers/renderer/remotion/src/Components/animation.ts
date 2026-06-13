import { Easing } from "remotion";

export const ANIM = {
  cardStart: 3,
  cardEnd: 18,
  titleStart: 6,
  titleEnd: 21,
  bodyStart: 11,
  bodyEnd: 26,
  imageStart: 5,
  imageEnd: 21,
  footerStart: 16,
  footerEnd: 29,
  rowDuration: 16,
  sectionLabelDuration: 11,
  rowStagger: 4,
} as const;

export const EASE_CARD = Easing.bezier(0.16, 1, 0.3, 1);
