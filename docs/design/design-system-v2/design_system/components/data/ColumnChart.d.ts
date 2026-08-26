import * as React from 'react';

export interface ColumnDatum {
  label: string;
  value: number;
  /** Force emphasis. Defaults to the last column (the current period). */
  emphasis?: boolean;
}

/**
 * Bare column chart for a short time series — the AQ history. No axes, no gridlines:
 * the values sit above the columns. The current period is the only accented column.
 *
 * @startingPoint section="Data" subtitle="Six-month AQ history" viewport="700x200"
 */
export interface ColumnChartProps {
  data: ColumnDatum[];
  /** Overall block height in px. Default 96. */
  height?: number;
  /** Scale ceiling. Defaults to max × 1.12. */
  max?: number;
  gap?: string;
  showValues?: boolean;
  ariaLabel?: string;
}

export function ColumnChart(props: ColumnChartProps): JSX.Element;
