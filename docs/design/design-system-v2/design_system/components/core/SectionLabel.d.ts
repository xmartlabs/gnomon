import * as React from 'react';

/**
 * The mono uppercase eyebrow that titles every block. Because it replaced card headers
 * throughout this system, it is also what carries the document outline: pass `as` to
 * render a real heading. Definitions belong in `hint`, never beside the label.
 */
export interface SectionLabelProps {
  children: React.ReactNode;
  /**
   * Element to render. Default 'div' — correct for decorative eyebrows that repeat a
   * figure's name ("TOKENS · COSTO"). Pass 'h2'/'h3' for any label that titles a real
   * section, keeping the page's h1 → h2 → h3 order intact.
   */
  as?: 'h2' | 'h3' | 'h4' | 'div';
  /** Explanatory copy — rendered as a keyboard-reachable Tooltip. */
  hint?: string;
  size?: 'sm' | 'lg';
  tight?: boolean;
  trailing?: React.ReactNode;
}

export function SectionLabel(props: SectionLabelProps): JSX.Element;
