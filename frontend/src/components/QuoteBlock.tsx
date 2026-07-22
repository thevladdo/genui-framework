/**
 * QuoteBlock: a single large editorial quote / manifesto.
 */

import React from 'react';
import type { QuoteData } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface QuoteBlockProps {
  data: QuoteData;
  className?: string;
}

export const QuoteBlock: React.FC<QuoteBlockProps> = ({ data, className = '' }) => {
  const { quote, author, role, avatarUrl, logoUrl, logoLabel } = data;

  if (!quote) return null;

  const logo = sanitizeUrl(logoUrl);
  const avatar = author ? sanitizeUrl(avatarUrl) : undefined;
  const hasAttribution = Boolean(author || role);

  return (
    <figure className={`genui-quote ${className}`.trim()}>
      {logo ? (
        <div className="genui-quote__logo">
          <img src={logo} alt={logoLabel ?? ''} />
        </div>
      ) : logoLabel ? (
        <div className="genui-quote__logo">
          <span className="genui-quote__logo-label">{logoLabel}</span>
        </div>
      ) : null}

      <blockquote className="genui-quote__text">“{quote}”</blockquote>

      {hasAttribution && (
        <figcaption className="genui-quote__attribution">
          {avatar && (
            <img className="genui-quote__avatar" src={avatar} alt="" />
          )}
          {(author || role) && (
            <span className="genui-quote__meta">
              {author && <cite className="genui-quote__author">{author}</cite>}
              {role && <span className="genui-quote__role">{role}</span>}
            </span>
          )}
        </figcaption>
      )}
    </figure>
  );
};

export default QuoteBlock;
