import * as React from 'react';

/**
 * Small classifying label — tiers, states, counts. Outlined by default.
 *
 * @startingPoint section="Core" subtitle="Tier and status badges" viewport="700x150"
 */
export interface BadgeProps {
  children: React.ReactNode;
  tone?: 'neutral' | 'accent' | 'solid' | 'positive' | 'negative' | 'warning';
  uppercase?: boolean;
}

export function Badge(props: BadgeProps): JSX.Element;
