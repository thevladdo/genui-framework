/**
 * HeroBanner: parametric hero section.
 *
 * Variants degrade in a chain: "split" without a usable image falls back
 * to "centered"; "centered" without an image keeps its accent gradient
 * background (defined in CSS). No variant ever renders an empty pane.
 */

import React from 'react';
import type { HeroBannerData } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface HeroBannerProps {
  data: HeroBannerData;
  className?: string;
}

export const HeroBanner: React.FC<HeroBannerProps> = ({ data, className = '' }) => {
  const { badge, headline, subheadline, primaryCta, secondaryCta } = data;

  if (!headline) return null;

  const imageUrl = sanitizeUrl(data.imageUrl);
  const variant =
    data.variant === 'split' && !imageUrl ? 'centered' : data.variant ?? 'centered';

  const primaryUrl = sanitizeUrl(primaryCta?.url);
  const secondaryUrl = sanitizeUrl(secondaryCta?.url);

  const ctas = (primaryUrl || secondaryUrl) && (
    <div className="genui-hero__ctas">
      {primaryCta?.label && primaryUrl && (
        <a className="genui-hero__cta" href={primaryUrl}>
          {primaryCta.label}
        </a>
      )}
      {secondaryCta?.label && secondaryUrl && (
        <a className="genui-hero__cta genui-hero__cta--secondary" href={secondaryUrl}>
          {secondaryCta.label}
        </a>
      )}
    </div>
  );

  const text = (
    <div className="genui-hero__content">
      {badge && <span className="genui-hero__badge">{badge}</span>}
      <h1 className="genui-hero__headline">{headline}</h1>
      {subheadline && <p className="genui-hero__subheadline">{subheadline}</p>}
      {ctas}
    </div>
  );

  if (variant === 'split') {
    return (
      <section className={`genui-hero genui-hero--split ${className}`.trim()}>
        {text}
        <img className="genui-hero__image" src={imageUrl} alt="" />
      </section>
    );
  }

  if (variant === 'minimal') {
    return (
      <section className={`genui-hero genui-hero--minimal ${className}`.trim()}>
        {text}
      </section>
    );
  }

  return (
    <section className={`genui-hero genui-hero--centered ${className}`.trim()}>
      {imageUrl && <img className="genui-hero__bg" src={imageUrl} alt="" aria-hidden="true" />}
      {text}
    </section>
  );
};

export default HeroBanner;
