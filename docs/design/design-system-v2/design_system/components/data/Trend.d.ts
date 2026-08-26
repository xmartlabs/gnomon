import * as React from 'react';

/**
 * Signed change indicator. Always renders a glyph AND a number, so it survives
 * greyscale and colour-blindness — colour is never the only carrier.
 */
export interface TrendProps {
  /** Positive, negative, 0, or null/undefined for "no data". */
  delta?: number | null;
  /** Comparison period, e.g. "July". */
  against?: string;
  size?: 'sm' | 'lg';
}

export function Trend(props: TrendProps): JSX.Element;
