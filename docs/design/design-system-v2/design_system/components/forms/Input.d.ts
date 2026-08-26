import * as React from 'react';

/** Single-line text field. Label is always visible — placeholders never stand in for one. */
export interface InputProps {
  label: string;
  name?: string;
  id?: string;
  value?: string;
  type?: 'text' | 'email' | 'password' | 'search' | 'url';
  placeholder?: string;
  /** Always set for known fields: 'name', 'email', 'off'. */
  autoComplete?: string;
  required?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  /** Renders the value in the figure font — for tokens, ids, codes. */
  mono?: boolean;
  /** Specific and actionable, e.g. "That is not an email — check for a missing @". */
  error?: string;
  hint?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export function Input(props: InputProps): JSX.Element;
