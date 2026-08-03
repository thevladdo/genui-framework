/**
 * StatsBanner: numeric metrics ("10M users", "99.9% uptime").
 * Pure text by design: the LLM populates values from RAG context.
 */

import React from 'react';
import type { MovingStat, StatChange, StatsBannerData } from '../types';

export interface StatsBannerProps {
  data: StatsBannerData;
  className?: string;
}

const Arrow: React.FC<{ direction: StatChange['direction'] }> = ({ direction }) => (
  <svg
    className="genui-stats__arrow"
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
    {direction === 'up' ? (
      <>
        <path d="M5 11 11 5" />
        <path d="M6 5h5v5" />
      </>
    ) : (
      <>
        <path d="M11 5 5 11" />
        <path d="M10 11H5V6" />
      </>
    )}
  </svg>
);

const Metric: React.FC<{ stat: MovingStat }> = ({ stat }) => {
  const change = stat.change;
  const tone = change?.sentiment === 'good' || change?.sentiment === 'bad'
    ? ` genui-stats__item--${change.sentiment}`
    : '';

  return (
    <div className={`genui-stats__item${tone}`}>
      {change && (
        <span className="genui-stats__movement">
          <Arrow direction={change.direction} />
          <span className="genui-sr-only">{change.direction}</span>
        </span>
      )}
      <p className="genui-stats__value">
        {stat.value}
        {change?.value && <span className="genui-stats__change">{change.value}</span>}
      </p>
      <p className="genui-stats__label">{stat.label}</p>
      {stat.description && (
        <p className="genui-stats__description">{stat.description}</p>
      )}
    </div>
  );
};

export const StatsBanner: React.FC<StatsBannerProps> = ({ data, className = '' }) => {
  const { stats, columns, eyebrow, title, description, layout } = data;

  if (!Array.isArray(stats) || stats.length === 0) return null;

  const narration = Boolean(eyebrow || title || description);
  const split = layout === 'split' && narration;
  const cols = Math.max(
    1,
    Math.min(columns ?? (split ? 2 : stats.length), stats.length, split ? 2 : 4),
  );

  const metrics = stats.map((stat, i) => <Metric key={`${stat.label}-${i}`} stat={stat} />);

  if (!split) {
    return (
      <section
        className={`genui-stats ${className}`.trim()}
        style={{ ['--genui-stats-cols' as string]: cols }}
      >
        {metrics}
      </section>
    );
  }

  return (
    <section className={`genui-stats genui-stats--split ${className}`.trim()}>
      <div className="genui-stats__intro">
        {eyebrow && <span className="genui-stats__eyebrow">{eyebrow}</span>}
        {title && <h2 className="genui-stats__title">{title}</h2>}
        {description && <p className="genui-stats__intro-text">{description}</p>}
      </div>
      <div
        className="genui-stats__grid"
        style={{ ['--genui-stats-cols' as string]: cols }}
      >
        {metrics}
      </div>
    </section>
  );
};

export default StatsBanner;
