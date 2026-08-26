import * as React from 'react';

export interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right';
  /** Render in the figure font with tabular numerals. */
  figure?: boolean;
  /** Secondary text colour and smaller size. */
  muted?: boolean;
  wrap?: boolean;
  render?: (row: any) => React.ReactNode;
}

/**
 * Rule-only table. No outer border, no zebra striping — hairlines and alignment
 * carry the structure. When `onRowClick` is set, every row gets a persistently
 * visible action link, so the affordance never depends on hover.
 *
 * @startingPoint section="Data" subtitle="People table with tiers, trends and row actions" viewport="700x300"
 */
export interface DataTableProps {
  columns: DataTableColumn[];
  rows: any[];
  onRowClick?: (row: any) => void;
  /** Text of the always-visible row action. Default "Open". */
  actionLabel?: string;
  /** Builds each row's aria-label when rows are clickable. */
  rowLabel?: (row: any) => string;
}

export function DataTable(props: DataTableProps): JSX.Element;
