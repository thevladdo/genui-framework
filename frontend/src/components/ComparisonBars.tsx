/**
 * ComparisonBars: figures set side by side, one of them the page's own.
 */

import React from 'react';
import type { ComparisonBar, ComparisonBarsData } from '../types';

export interface ComparisonBarsProps {
  data: ComparisonBarsData;
  className?: string;
}

const formatValue = (value: number, suffix?: string): string =>
  `${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}${suffix ?? ''}`;

const Bar: React.FC<{ bar: ComparisonBar; value: number; percent: number }> = ({
  bar,
  value,
  percent,
}) => {
  const highlighted = Boolean(bar.highlighted);
  const itemClass = `genui-compare__item ${highlighted ? 'genui-compare__item--highlight' : ''}`.trim();

  return (
    <li
      className={itemClass}
      aria-current={highlighted ? 'true' : undefined}
      style={{ ['--genui-compare-height' as string]: `${percent}%` }}
    >
      <div className="genui-compare__track">
        <div className="genui-compare__column">
          {highlighted &&
            (bar.callout ? (
              <p className="genui-compare__callout">{bar.callout}</p>
            ) : (
              <span className="genui-compare__marker" aria-hidden="true" />
            ))}
          <span className="genui-compare__value">{formatValue(value, bar.suffix)}</span>
          <div className="genui-compare__bar" />
        </div>
      </div>
      <p className="genui-compare__label">{bar.label}</p>
    </li>
  );
};

export const ComparisonBars: React.FC<ComparisonBarsProps> = ({ data, className = '' }) => {
  const { title, subtitle, bars } = data;

  if (!Array.isArray(bars) || bars.length === 0) return null;

  const values = bars.map((bar) => Number(bar.value));
  if (!values.every((value) => Number.isFinite(value) && value >= 0)) return null;

  const max = Math.max(...values);
  const hasCallout = bars.some((bar) => bar.highlighted && bar.callout);
  const chartClass = `genui-compare__chart ${hasCallout ? 'genui-compare__chart--callout' : ''}`.trim();

  return (
    <section className={`genui-compare ${className}`.trim()}>
      {(title || subtitle) && (
        <header className="genui-compare__header">
          {title && <h2 className="genui-compare__title">{title}</h2>}
          {subtitle && <p className="genui-compare__subtitle">{subtitle}</p>}
        </header>
      )}
      <ul className={chartClass}>
        {bars.map((bar, i) => (
          <Bar
            key={`${bar.label}-${i}`}
            bar={bar}
            value={values[i]}
            percent={max > 0 ? Math.max((values[i] / max) * 100, 2) : 2}
          />
        ))}
      </ul>
    </section>
  );
};

export default ComparisonBars;
