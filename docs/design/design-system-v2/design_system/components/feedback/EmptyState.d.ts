import * as React from 'react';

/**
 * What a screen shows when there is nothing to measure. Left-aligned, typographic,
 * with a recovery action — never a centred illustration.
 *
 * @startingPoint section="Feedback" subtitle="Empty month with a recovery action" viewport="700x260"
 */
export interface EmptyStateProps {
  /** Plain-language sentence: "Nobody uploaded sessions in June 2026." */
  title: string;
  /** What to do about it. May contain inline code. */
  body?: React.ReactNode;
  /** Usually a `Button variant="link"` back to a period with data. */
  action?: React.ReactNode;
  label?: string;
  /**
   * Heading level for the title. Default 'h2', assuming a screen h1 sits above it.
   * Pass 'h1' when the empty state IS the whole screen and nothing else titles it.
   */
  titleAs?: 'h1' | 'h2';
  width?: number;
}

export function EmptyState(props: EmptyStateProps): JSX.Element;
