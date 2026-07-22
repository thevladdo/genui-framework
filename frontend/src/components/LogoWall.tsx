/**
 * LogoWall: a grid of logos (clients, technologies, partners).
 */

import React from 'react';
import type { LogoWallData, LogoItem } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface LogoWallProps {
  data: LogoWallData;
  className?: string;
}

const Logo: React.FC<{ logo: LogoItem }> = ({ logo }) => {
  const src = sanitizeUrl(logo.imageUrl);
  if (!src) return null;
  const href = sanitizeUrl(logo.url);
  const img = <img className="genui-logowall__logo" src={src} alt={logo.alt} />;
  return href ? (
    <a className="genui-logowall__item" href={href} aria-label={logo.alt}>
      {img}
    </a>
  ) : (
    <div className="genui-logowall__item">{img}</div>
  );
};

export const LogoWall: React.FC<LogoWallProps> = ({ data, className = '' }) => {
  const { heading, logos, ctaLabel, ctaUrl } = data;

  const visible = (Array.isArray(logos) ? logos : []).filter((l) =>
    sanitizeUrl(l.imageUrl),
  );
  if (visible.length === 0) return null;

  const ctaHref = sanitizeUrl(ctaUrl);
  const hasReveal = Boolean(ctaHref && ctaLabel);

  return (
    <section
      className={`genui-logowall ${hasReveal ? 'genui-logowall--reveal' : ''} ${className}`.trim()}
    >
      {heading && <p className="genui-logowall__heading">{heading}</p>}

      <div className="genui-logowall__inner">
        {hasReveal && (
          <a className="genui-logowall__cta" href={ctaHref}>
            {ctaLabel}
            <span aria-hidden="true"> →</span>
          </a>
        )}
        <div className="genui-logowall__grid">
          {visible.map((logo, i) => (
            <Logo key={`${logo.alt}-${i}`} logo={logo} />
          ))}
        </div>
      </div>
    </section>
  );
};

export default LogoWall;
