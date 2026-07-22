/**
 * CaseStudies: editorial project / case studies.
 */

import React, { useEffect, useRef, useState } from 'react';
import type { CaseStudiesData, CaseStudyItem, CaseStudyMetric } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface CaseStudiesProps {
  data: CaseStudiesData;
  className?: string;
}

interface ParsedMetric {
  animatable: boolean;
  prefix: string;
  end: number;
  suffix: string;
  decimals: number;
  raw: string;
}

const parseMetric = (raw: string): ParsedMetric => {
  const value = (raw ?? '').toString().trim();
  const m = value.match(/^([^\d\-+]*?)\s*([-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([^\d\s]*)$/);
  if (!m) return { animatable: false, prefix: '', end: 0, suffix: '', decimals: 0, raw: value };
  const [, prefix, num, suffix] = m;
  const normalized = num.replace(/,/g, '');
  const end = parseFloat(normalized);
  if (Number.isNaN(end)) {
    return { animatable: false, prefix: '', end: 0, suffix: '', decimals: 0, raw: value };
  }
  return {
    animatable: true,
    prefix: prefix ?? '',
    end,
    suffix: suffix ?? '',
    decimals: normalized.split('.')[1]?.length ?? 0,
    raw: value,
  };
};

const AnimatedValue: React.FC<{ value: string }> = ({ value }) => {
  const parsed = parseMetric(value);
  const ref = useRef<HTMLParagraphElement>(null);
  // null = show the raw input verbatim (SSR, default, and the final frame,
  // so the displayed value equals the input exactly). A number = mid-tween.
  const [tween, setTween] = useState<number | null>(null);

  useEffect(() => {
    if (!parsed.animatable) return;
    const el = ref.current;
    if (!el || typeof window === 'undefined' || !('IntersectionObserver' in window)) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) return;

    let raf = 0;
    let started = false;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting || started) return;
        started = true;
        io.disconnect();
        setTween(0);
        const t0 = performance.now();
        const tick = (now: number) => {
          const p = Math.min((now - t0) / 1200, 1);
          if (p < 1) {
            setTween(parsed.end * (1 - Math.pow(1 - p, 3)));
            raf = requestAnimationFrame(tick);
          } else {
            setTween(null);
          }
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.3 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [parsed.animatable, parsed.end]);

  const content =
    tween === null
      ? parsed.raw
      : `${parsed.prefix}${tween.toLocaleString('en-US', {
        minimumFractionDigits: parsed.decimals,
        maximumFractionDigits: parsed.decimals,
      })}${parsed.suffix}`;

  return (
    <p ref={ref} className="genui-cases__metric-value" aria-label={parsed.raw}>
      {content}
    </p>
  );
};

const Metric: React.FC<{ metric: CaseStudyMetric }> = ({ metric }) => (
  <div className="genui-cases__metric">
    <AnimatedValue value={metric.value} />
    <p className="genui-cases__metric-label">{metric.label}</p>
    {metric.description && (
      <p className="genui-cases__metric-desc">{metric.description}</p>
    )}
  </div>
);

const Case: React.FC<{ item: CaseStudyItem; reversed: boolean }> = ({ item, reversed }) => {
  const image = sanitizeUrl(item.imageUrl);
  const metrics = Array.isArray(item.metrics) ? item.metrics : [];
  const caseClass = `genui-cases__case ${reversed ? 'genui-cases__case--reversed' : ''}`.trim();

  return (
    <article className={caseClass}>
      <div className="genui-cases__main">
        {image && (
          <div className="genui-cases__media">
            <img src={image} alt="" loading="lazy" />
          </div>
        )}
        <div className="genui-cases__body">
          <div className="genui-cases__text">
            <h3 className="genui-cases__title">{item.title}</h3>
            {item.summary && <p className="genui-cases__summary">{item.summary}</p>}
          </div>
          {(item.name || item.role) && (
            <p className="genui-cases__attribution">
              {item.name && <span className="genui-cases__name">{item.name}</span>}
              {item.role && <span className="genui-cases__role">{item.role}</span>}
            </p>
          )}
        </div>
      </div>
      {metrics.length > 0 && (
        <div className="genui-cases__metrics">
          {metrics.map((metric, i) => (
            <Metric key={`${metric.label}-${i}`} metric={metric} />
          ))}
        </div>
      )}
    </article>
  );
};

export const CaseStudies: React.FC<CaseStudiesProps> = ({ data, className = '' }) => {
  const { heading, subheading, cases } = data;

  if (!Array.isArray(cases) || cases.length === 0) return null;

  return (
    <section className={`genui-cases ${className}`.trim()}>
      {(heading || subheading) && (
        <header className="genui-cases__header">
          {heading && <h2 className="genui-cases__heading">{heading}</h2>}
          {subheading && <p className="genui-cases__subheading">{subheading}</p>}
        </header>
      )}
      <div className="genui-cases__list">
        {cases.map((item, i) => (
          <Case key={`${item.title}-${i}`} item={item} reversed={i % 2 === 1} />
        ))}
      </div>
    </section>
  );
};

export default CaseStudies;
