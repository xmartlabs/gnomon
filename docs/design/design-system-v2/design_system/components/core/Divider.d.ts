import * as React from 'react';

/** A hairline. The primary way sections are separated in gnomon — used instead of cards. */
export interface DividerProps {
  orientation?: 'horizontal' | 'vertical';
  weight?: 'strong' | 'default' | 'subtle';
  /** Doubles a strong rule to 2px. */
  thick?: boolean;
  /** Spacing token index for vertical margin, e.g. 9 -> --space-9. Default 11 (48px). */
  space?: number;
}

export function Divider(props: DividerProps): JSX.Element;
