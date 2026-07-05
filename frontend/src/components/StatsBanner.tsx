/**
 * StatsBanner: numeric metrics grid ("10M users", "99.9% uptime").
 * Pure text by design: the LLM populates values from RAG context.
 */

import React from 'react';
import type { StatsBannerData } from '../types';

export interface StatsBannerProps {
  data: StatsBannerData;
  className?: string;
}

export const StatsBanner: React.FC<StatsBannerProps> = ({ data, className = '' }) => {
  const { stats, columns } = data;

  if (!Array.isArray(stats) || stats.length === 0) return null;

  const cols = columns ?? Math.min(stats.length, 4);

  return (
    <section
      className={`genui-stats ${className}`.trim()}
      style={{ ['--genui-stats-cols' as string]: cols }}
    >
      {stats.map((stat, i) => (
        <div key={`${stat.label}-${i}`} className="genui-stats__item">
          <p className="genui-stats__value">{stat.value}</p>
          <p className="genui-stats__label">{stat.label}</p>
          {stat.description && (
            <p className="genui-stats__description">{stat.description}</p>
          )}
        </div>
      ))}
    </section>
  );
};

export default StatsBanner;
