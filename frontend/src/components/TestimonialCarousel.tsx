/**
 * TestimonialCarousel: quotes with optional avatar.
 *
 * Hand-rolled (useState + optional autoplay): a fade between quotes does
 * not justify a carousel library. Degradation rules:
 * - one testimonial -> static card, no arrows/dots
 * - missing avatarUrl -> accent circle with the person's initials
 */

import React, { useEffect, useState } from 'react';
import type { TestimonialCarouselData } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface TestimonialCarouselProps {
  data: TestimonialCarouselData;
  className?: string;
}

const initialsOf = (name: string): string =>
  name
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();

export const TestimonialCarousel: React.FC<TestimonialCarouselProps> = ({
  data,
  className = '',
}) => {
  const { testimonials, autoplay = false, interval = 6000 } = data;
  const [active, setActive] = useState(0);
  const count = Array.isArray(testimonials) ? testimonials.length : 0;

  useEffect(() => {
    if (!autoplay || count < 2) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const timer = setInterval(
      () => setActive((current) => (current + 1) % count),
      Math.max(interval, 2500),
    );
    return () => clearInterval(timer);
  }, [autoplay, interval, count]);

  if (count === 0) return null;

  const item = testimonials[Math.min(active, count - 1)];
  const avatarUrl = sanitizeUrl(item.avatarUrl);
  const meta = [item.role, item.company].filter(Boolean).join(' · ');

  return (
    <section className={`genui-testimonials ${className}`.trim()}>
      <blockquote className="genui-testimonials__quote">
        “{item.quote}”
      </blockquote>

      <div className="genui-testimonials__person">
        {avatarUrl ? (
          <img className="genui-testimonials__avatar" src={avatarUrl} alt="" />
        ) : (
          <span className="genui-testimonials__initials" aria-hidden="true">
            {initialsOf(item.name)}
          </span>
        )}
        <div className="genui-testimonials__meta">
          <div className="genui-testimonials__name">{item.name}</div>
          {meta && <div className="genui-testimonials__role">{meta}</div>}
        </div>
      </div>

      {count > 1 && (
        <div className="genui-testimonials__controls">
          <button
            type="button"
            className="genui-testimonials__arrow"
            aria-label="Previous testimonial"
            onClick={() => setActive((active - 1 + count) % count)}
          >
            ←
          </button>
          <div className="genui-testimonials__dots">
            {testimonials.map((_, i) => (
              <button
                key={i}
                type="button"
                className="genui-testimonials__dot"
                aria-label={`Testimonial ${i + 1}`}
                aria-current={i === active}
                onClick={() => setActive(i)}
              />
            ))}
          </div>
          <button
            type="button"
            className="genui-testimonials__arrow"
            aria-label="Next testimonial"
            onClick={() => setActive((active + 1) % count)}
          >
            →
          </button>
        </div>
      )}
    </section>
  );
};

export default TestimonialCarousel;
