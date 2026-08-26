import * as React from 'react';

/**
 * Labelled horizontal bar for a scored dimension — the four AQ pillars, rubric axes,
 * model share. Optional `reference` draws a tick for the team average.
 *
 * @startingPoint section="Data" subtitle="Scored bars with weight, value and reference tick" viewport="700x230"
 */
export interface PillarBarProps {
  name: string;
  value: number;
  /** Denominator. Default 100. */
  max?: number;
  /** Weight caption, e.g. "30%". */
  weight?: string;
  /** Draws a 2px comparison tick, e.g. the team average. */
  reference?: number | null;
  size?: 'sm' | 'md' | 'lg';
  tone?: 'default' | 'muted';
}

export function PillarBar(props: PillarBarProps): JSX.Element;
