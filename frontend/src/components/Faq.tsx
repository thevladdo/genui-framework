/**
 * Faq.
 * 
 * NO FAQPage structured data here, deliberately. The zone already emits
 * a JSON-LD block declaring that this content was written by a model
 * (see disclosureJsonLd). A second block telling search engines that
 * these are the site's official frequently asked questions would make
 * two opposite claims about the same text, and the framework cannot
 * stand behind the second one for prose a model composed.
 */

import React from 'react';
import type { FaqData } from '../types';
import { SafeMarkdown } from './SafeMarkdown';

export interface FaqProps {
  data: FaqData;
  className?: string;
}

export const Faq: React.FC<FaqProps> = ({ data, className = '' }) => {
  const { title, intro, items } = data;
  const group = `genui-faq-${React.useId()}`;

  const entries = Array.isArray(items)
    ? items.filter((item) => item && item.question && item.answer)
    : [];
  if (entries.length === 0) return null;

  return (
    <section className={`genui-faq ${className}`.trim()}>
      {(title || intro) && (
        <header className="genui-faq__header">
          {title && <h2 className="genui-faq__title">{title}</h2>}
          {intro && <p className="genui-faq__intro">{intro}</p>}
        </header>
      )}

      <div className="genui-faq__list">
        {entries.map((item, i) => (
          <details className="genui-faq__item" name={group} key={`${item.question}-${i}`}>
            <summary className="genui-faq__question">
              <span>{item.question}</span>
              <svg
                className="genui-faq__marker"
                viewBox="0 0 16 16"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="m4 6 4 4 4-4" />
              </svg>
            </summary>
            <div className="genui-faq__answer">
              <SafeMarkdown>{item.answer}</SafeMarkdown>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
};

export default Faq;
