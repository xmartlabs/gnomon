import * as React from 'react';

/**
 * A figure with its label. The largest figure on a screen is its headline — gnomon
 * builds hierarchy with type size, not with containers.
 *
 * @startingPoint section="Data" subtitle="Metric sizes with unit, trend and caption" viewport="700x220"
 */
export interface MetricProps {
  value: React.ReactNode;
  /** Mono uppercase eyebrow above the figure. */
  label?: string;
  /** e.g. "/100", "tokens". Rendered small and secondary. */
  unit?: string;
  /** Usually a `Trend`. */
  trailing?: React.ReactNode;
  caption?: string;
  size?: 'xl' | 'lg' | 'md' | 'sm';
  tone?: 'default' | 'accent';
  align?: 'left' | 'right';
}

export function Metric(props: MetricProps): JSX.Element;
