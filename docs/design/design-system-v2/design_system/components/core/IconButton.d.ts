import * as React from 'react';

/** Square icon-only control. `ariaLabel` is mandatory — the glyph carries no text. */
export interface IconButtonProps {
  /** A single 16-20px stroke icon (Lucide). */
  children: React.ReactNode;
  /** Required. Also used as the native tooltip. */
  ariaLabel: string;
  size?: 'sm' | 'md' | 'lg';
  bordered?: boolean;
  pressed?: boolean;
  disabled?: boolean;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
}

export function IconButton(props: IconButtonProps): JSX.Element;
