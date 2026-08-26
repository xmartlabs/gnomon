import * as React from 'react';

/**
 * Keyboard-reachable explanation. Replaces the native `title` attribute, which is
 * unreachable by keyboard and invisible on touch. Renders its own `i` marker when
 * no children are passed.
 */
export interface TooltipProps {
  /** The explanation. Full sentences. */
  label: string;
  /** The trigger. Omit to get the default `i` marker. */
  children?: React.ReactNode;
  side?: 'top' | 'bottom' | 'right';
  width?: number;
}

export function Tooltip(props: TooltipProps): JSX.Element;
