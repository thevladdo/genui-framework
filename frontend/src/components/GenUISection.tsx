/**
 * GenUISection
 * Main wrapper component that provides theming and context
 */

import React, { useMemo } from 'react';
import type { GenUISectionProps, GenUITheme } from '../types';
import '../styles/genui.css';

const DEFAULT_THEME: GenUITheme = {
  carouselNumOfSlides: 4,
  carouselAutoRotate: false,
  borderRadius: '30px',
  primaryColor: '#fafafa',
  secondaryColor: '#b2b2b2',
  backgroundColor: 'transparent',
  textColor: '#1a1a1a',
  accentColor: '#3b82f6',
  fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  fontSize: '16px',
};

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
  const mergedTheme = useMemo(() => ({
    ...DEFAULT_THEME,
    ...theme,
  }), [theme]);

  const cssVars = useMemo(() =>
    themeToCSSVars(mergedTheme),
    [mergedTheme]
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
