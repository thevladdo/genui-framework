/**
 * GenUISection
 * Main wrapper component that provides theming and context
 */

import React, { useMemo } from 'react';
import type { GenUISectionProps, GenUITheme } from '../types';
import '../styles/genui.css';

/**
 * Emit ONLY the CSS variables explicitly provided in `theme`.
 *
 * Defaults live in genui.css (:root), never here — so a GenUISection
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
  }
  if (theme.accentColor) {
    vars['--genui-accent-color'] = theme.accentColor;
  }
  if (theme.borderRadius) {
    vars['--genui-border-radius'] = theme.borderRadius;
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
    >
      {children}
    </section>
  );
};

export default GenUISection;
