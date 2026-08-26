import * as React from 'react';

/** Native select. `variant="inline"` is the underlined, chrome-less version used in page headers. */
export interface SelectProps {
  options: Array<string | { value: string; label: string }>;
  value?: string;
  label?: string;
  name?: string;
  id?: string;
  variant?: 'bordered' | 'inline';
  disabled?: boolean;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
}

export function Select(props: SelectProps): JSX.Element;
