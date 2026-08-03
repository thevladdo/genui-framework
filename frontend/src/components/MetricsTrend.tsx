/**
 * MetricsTrend: how big, and how it got there.
 *
 * The curve is a custom/hand written SVG path.
 */

import React from 'react';
import type { MetricsTrendData } from '../types';

export interface MetricsTrendProps {
  data: MetricsTrendData;
  className?: string;
}

const HEIGHT = 30;
const PAD = 2;

const paths = (values: number[]): { line: string; area: string } => {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((value, i) => {
    const x = (i / (values.length - 1)) * 100;
    const y = HEIGHT - PAD - ((value - min) / range) * (HEIGHT - PAD * 2);
    return `${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  const line = `M ${points.join(' L ')}`;
  return { line, area: `${line} L 100 ${HEIGHT} L 0 ${HEIGHT} Z` };
};

export const MetricsTrend: React.FC<MetricsTrendProps> = ({ data, className = '' }) => {
  const { title, tail, metrics, series } = data;
  const gradientId = `genui-trend-${React.useId().replace(/:/g, '')}`;

  if (!Array.isArray(metrics) || metrics.length === 0) return null;

  const points = Array.isArray(series) ? series : [];
  const values = points.map((point) => Number(point.value));
  const drawable = points.length >= 2 && values.every((v) => Number.isFinite(v));
  const shape = drawable ? paths(values) : null;

  return (
    <section className={`genui-metrics ${className}`.trim()}>
      <h2 className="genui-metrics__title">
        {title}
        {tail && <span className="genui-metrics__tail"> {tail}</span>}
      </h2>

      <div
        className="genui-metrics__grid"
        style={{ ['--genui-metrics-cols' as string]: Math.min(metrics.length, 4) }}
      >
        {metrics.map((metric, i) => (
          <div className="genui-metrics__item" key={`${metric.label}-${i}`}>
            <p className="genui-metrics__value">{metric.value}</p>
            <p className="genui-metrics__label">{metric.label}</p>
            {metric.description && (
              <p className="genui-metrics__description">{metric.description}</p>
            )}
          </div>
        ))}
      </div>

      {shape && (
        <figure className="genui-metrics__trend">
          <svg
            className="genui-metrics__curve"
            viewBox={`0 0 100 ${HEIGHT}`}
            preserveAspectRatio="none"
            aria-hidden="true"
            focusable="false"
          >
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" className="genui-metrics__stop-from" />
                <stop offset="100%" className="genui-metrics__stop-to" />
              </linearGradient>
            </defs>
            <path className="genui-metrics__area" d={shape.area} fill={`url(#${gradientId})`} />
            <path
              className="genui-metrics__line"
              d={shape.line}
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          <figcaption className="genui-metrics__ends">
            <span>{points[0].label}</span>
            <span>{points[points.length - 1].label}</span>
          </figcaption>
          <ul className="genui-sr-only">
            {points.map((point, i) => (
              <li key={`${point.label}-${i}`}>
                {point.label}: {point.value}
              </li>
            ))}
          </ul>
        </figure>
      )}
    </section>
  );
};

export default MetricsTrend;
