/**
 * StepsSection: animated step sequence (onboarding, purchase flow).
 *
 * Autoplay advances via a keyed CSS progress bar + setInterval; it is
 * disabled under prefers-reduced-motion and pauses while hovered.
 * layout "text-only" drops the side image column entirely (full-width
 * list) instead of rendering an empty pane.
 */

import React, { useEffect, useRef, useState } from 'react';
import type { StepsSectionData } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface StepsSectionProps {
  data: StepsSectionData;
  className?: string;
}

const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export const StepsSection: React.FC<StepsSectionProps> = ({ data, className = '' }) => {
  const { layout, steps, autoplay = false, interval = 4000 } = data;
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const stepsCount = Array.isArray(steps) ? steps.length : 0;
  const reduced = useRef(prefersReducedMotion());

  useEffect(() => {
    if (!autoplay || paused || reduced.current || stepsCount < 2) return;
    const timer = setInterval(
      () => setActive((current) => (current + 1) % stepsCount),
      Math.max(interval, 1500),
    );
    return () => clearInterval(timer);
  }, [autoplay, paused, interval, stepsCount]);

  if (stepsCount === 0) return null;

  const current = steps[Math.min(active, stepsCount - 1)];
  const imageUrl =
    layout === 'with-image' ? sanitizeUrl(current.imageUrl) : undefined;
  const textOnly = !imageUrl;

  return (
    <section
      className={`genui-steps ${textOnly ? 'genui-steps--text-only' : ''} ${className}`.trim()}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div>
        {steps.map((step, i) => (
          <button
            key={`${step.title}-${i}`}
            type="button"
            className="genui-steps__item"
            aria-current={i === active ? 'step' : undefined}
            onClick={() => setActive(i)}
          >
            <span className="genui-steps__index">{i + 1}</span>
            <span>
              <span className="genui-steps__title">{step.title}</span>
              {step.description && (
                <p className="genui-steps__description">{step.description}</p>
              )}
              {i === active && autoplay && !reduced.current && (
                <span className="genui-steps__progress">
                  {/* Keyed remount restarts the width animation per step */}
                  <span
                    key={active}
                    className="genui-steps__progress-bar"
                    style={{
                      width: paused ? '0%' : '100%',
                      transitionDuration: `${Math.max(interval, 1500)}ms`,
                    }}
                  />
                </span>
              )}
            </span>
          </button>
        ))}
      </div>

      {imageUrl && (
        <img className="genui-steps__image" src={imageUrl} alt={current.title} />
      )}
    </section>
  );
};

export default StepsSection;
