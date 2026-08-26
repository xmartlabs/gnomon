import * as React from 'react';

export interface DonutSlice {
  label: string;
  value: number;
  /** Override the ordered green ramp. Rarely needed. */
  color?: string;
}

/**
 * Share-of-total chart with hover and keyboard inspection: the slice offsets 4px and
 * the value appears in the centre. The legend carries names only — percentages live
 * in the hover, keeping the resting state quiet.
 *
 * @startingPoint section="Data" subtitle="Model mix donut with hover inspection" viewport="700x260"
 */
export interface DonutChartProps {
  data: DonutSlice[];
  /** Outer diameter in px. Default 176. */
  size?: number;
  /** Ring thickness in viewBox units (0-46). Omit for a filled pie. */
  thickness?: number;
  /** Set false to hide the legend. */
  legend?: boolean;
  ariaLabel?: string;
}

export function DonutChart(props: DonutChartProps): JSX.Element;
