/**
 * GenUISection
 * Main wrapper component that provides theming and context
 */

import React, { useMemo } from 'react';
import type { GenUISectionProps, GenUITheme } from '../types';
import '../styles/genui.css';

const SPACING_BASE: Record<string, number> = {
  xs: 4, sm: 8, md: 16, lg: 24, xl: 32, '2xl': 48,
};

const SPACING_FACTORS: Record<NonNullable<GenUITheme['spacingScale']>, number> = {
  sm: 0.75,
  base: 1,
  lg: 1.25,
};

/**
 * Emit ONLY the CSS variables explicitly provided in `theme`.
 *
 * Defaults live in genui.css (:root), never here, so a GenUISection
 * nested inside another (e.g. the one GenUIZone wraps its content in)
 * with no theme of its own emits nothing and inherits the parent's
 * theme, instead of resetting everything to component-level defaults.
 */
const themeToCSSVars = (theme: GenUITheme): Record<string, string> => {
  const vars: Record<string, string> = {};

  if (theme.primaryColor) {
    vars['--genui-primary-color'] = theme.primaryColor;
  }
  if (theme.secondaryColor) {
    vars['--genui-secondary-color'] = theme.secondaryColor;
  }
  if (theme.backgroundColor) {
    vars['--genui-background-color'] = theme.backgroundColor;
  }
  if (theme.textColor) {
    vars['--genui-text-color'] = theme.textColor;
    vars['--genui-text-primary'] = theme.textColor;
  }
  if (theme.accentColor) {
    vars['--genui-accent-color'] = theme.accentColor;
  }
  if (theme.borderRadius) {
    // Both names: semantic tokens derived via var() in :root resolve THERE,
    // so per-subtree overrides must re-emit the semantic name too
    vars['--genui-border-radius'] = theme.borderRadius;
    vars['--genui-radius-md'] = theme.borderRadius;
  }
  if (theme.fontFamily) {
    vars['--genui-font-family'] = theme.fontFamily;
  }
  if (theme.fontSize) {
    vars['--genui-font-size-base'] = theme.fontSize;
  }
  if (theme.carouselNumOfSlides) {
    vars['--genui-carousel-slides'] = String(theme.carouselNumOfSlides);
  }
  if (theme.glassBlur) {
    vars['--genui-glass-blur'] = theme.glassBlur;
  }
  if (theme.surface1) {
    vars['--genui-surface-1'] = theme.surface1;
  }
  if (theme.surface2) {
    vars['--genui-surface-2'] = theme.surface2;
  }
  if (theme.surface3) {
    vars['--genui-surface-3'] = theme.surface3;
  }
  if (theme.textOnAccent) {
    vars['--genui-text-on-accent'] = theme.textOnAccent;
  }
  // Emitting the legacy radius tokens cascades into the semantic scale
  // (--genui-radius-sm/lg derive from them in :root)
  if (theme.radiusSm) {
    vars['--genui-border-radius-sm'] = theme.radiusSm;
    vars['--genui-radius-sm'] = theme.radiusSm;
  }
  if (theme.radiusLg) {
    vars['--genui-border-radius-lg'] = theme.radiusLg;
    vars['--genui-radius-lg'] = theme.radiusLg;
  }
  if (theme.radiusFull) {
    vars['--genui-radius-full'] = theme.radiusFull;
  }
  if (theme.fontWeightHeading) {
    vars['--genui-font-weight-heading'] = theme.fontWeightHeading;
  }
  if (theme.spacingScale && SPACING_FACTORS[theme.spacingScale] !== undefined) {
    const factor = SPACING_FACTORS[theme.spacingScale];
    for (const [step, px] of Object.entries(SPACING_BASE)) {
      vars[`--genui-spacing-${step}`] = `${Math.round(px * factor)}px`;
    }
  }

  return vars;
};

export const GenUISection: React.FC<GenUISectionProps> = ({
  children,
  theme = {},
  className = '',
  style = {},
}) => {
  const cssVars = useMemo(() =>
    themeToCSSVars(theme),
    [theme]
  );

  const combinedStyle: React.CSSProperties = useMemo(() => ({
    ...cssVars as React.CSSProperties,
    ...style,
  }), [cssVars, style]);

  return (
    <section
      className={`genui-section ${className}`.trim()}
      style={combinedStyle}
      // Activates the [data-theme] token blocks in genui.css; omitted when
      // unset so nested sections inherit the ancestor's mode
      data-theme={theme.mode}
    >
      {children}
    </section>
  );
};

export default GenUISection;
