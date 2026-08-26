import * as React from 'react';

/**
 * Primary action control. Four variants; `link` renders as inline underlined text.
 *
 * @startingPoint section="Core" subtitle="Button variants, sizes and states" viewport="700x180"
 */
export interface ButtonProps {
  children?: React.ReactNode;
  /** Visual weight. Default 'primary'. Only ONE primary per view. */
  variant?: 'primary' | 'secondary' | 'ghost' | 'link';
  /** Control height: 32 / 40 / 48px. Default 'md'. */
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  fullWidth?: boolean;
  type?: 'button' | 'submit' | 'reset';
  /** Required when the label is not descriptive on its own. */
  ariaLabel?: string;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
}

export function Button(props: ButtonProps): JSX.Element;
