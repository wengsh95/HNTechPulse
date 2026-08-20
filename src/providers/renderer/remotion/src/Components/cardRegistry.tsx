import React from "react";

import type { SceneElementData } from "../types";
import {
  AtmosphereCard,
  ClosingCard,
  CommentDualShot,
  CommentShot,
  CoverCard,
  DataNumberShot,
  EventCard,
  HeadlineShot,
  QuickNewsShot,
  SignalsShot,
  SourceEvidenceShot,
} from "./Elements";
import type { ChapterName } from "./design";
import { SHOT_TEMPLATE_CATALOG, type ShotTemplateElementType } from "./templateCatalog";

export type CardRendererProps = {
  elementProps: Record<string, unknown>;
  duration: number;
  width: number;
  height: number;
};

export type CardElementType = ShotTemplateElementType;

export type CardRegistryEntry = {
  component: React.FC<CardRendererProps>;
  chapter: ChapterName;
  marksStory?: boolean;
};

export const CARD_REGISTRY = {
  cover_card: {
    component: (props) => <CoverCard {...props} />,
    chapter: "cover",
  },
  headline_card: {
    component: (props) => <HeadlineShot {...props} />,
    chapter: "focus",
    marksStory: true,
  },
  event_card: {
    component: (props) => <EventCard {...props} />,
    chapter: "focus",
    marksStory: true,
  },
  atmosphere_card: {
    component: (props) => <AtmosphereCard {...props} />,
    chapter: "atmosphere",
  },
  source_evidence_card: {
    component: (props) => <SourceEvidenceShot {...props} />,
    chapter: "focus",
  },
  comment_card: {
    component: (props) => <CommentShot {...props} />,
    chapter: "atmosphere",
  },
  comment_dual_card: {
    component: (props) => <CommentDualShot {...props} />,
    chapter: "atmosphere",
  },
  data_number_card: {
    component: (props) => <DataNumberShot {...props} />,
    chapter: "focus",
  },
  quick_card: {
    component: (props) => <QuickNewsShot {...props} />,
    chapter: "focus",
    marksStory: true,
  },
  closing_card: {
    component: (props) => <ClosingCard {...props} />,
    chapter: "closing",
  },
  signals_card: {
    component: (props) => <SignalsShot {...props} />,
    chapter: "closing",
  },
} satisfies Record<CardElementType, CardRegistryEntry>;

export const getCardRegistryEntry = (elementType: string): CardRegistryEntry | undefined =>
  CARD_REGISTRY[elementType as CardElementType];

export const isStoryMarkerElement = (element: SceneElementData): boolean => {
  const entry = getCardRegistryEntry(element.element_type);
  if (entry?.marksStory) return true;

  // A storyboard may replace the original event_card with a visual-only
  // template such as data_number_card or comment_dual_card.  Preserve chapter
  // boundaries from the durable story_index instead of coupling navigation to
  // one particular visual component.
  return Boolean(
    entry &&
    entry.chapter !== "closing" &&
    element.props &&
    element.props.story_index !== undefined,
  );
};

export const cardChapterForElementType = (elementType: string): ChapterName =>
  getCardRegistryEntry(elementType)?.chapter ?? "focus";

export const getShotTemplate = (elementType: string) =>
  SHOT_TEMPLATE_CATALOG[elementType as CardElementType];
