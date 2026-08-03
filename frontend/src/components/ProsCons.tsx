/**
 * ProsCons: advantages and limits side by side.
 */

import React from 'react';
import type { ProsConsData } from '../types';
import { SafeMarkdown } from './SafeMarkdown';

export interface ProsConsProps {
  data: ProsConsData;
  className?: string;
}

const Mark: React.FC<{ tone: 'pro' | 'con' }> = ({ tone }) => (
  <svg
    className="genui-proscons__icon"
    viewBox="0 0 16 16"
    width="14"
    height="14"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {tone === 'pro' ? <path d="M3 8.5 6.5 12 13 4.5" /> : <path d="M4 4l8 8M12 4l-8 8" />}
  </svg>
);

const Column: React.FC<{ heading: string; items: string[]; tone: 'pro' | 'con' }> = ({
  heading,
  items,
  tone,
}) => (
  <div className={`genui-proscons__col genui-proscons__col--${tone}`}>
    <h3 className="genui-proscons__head">
      <Mark tone={tone} />
      <span>{heading}</span>
    </h3>
    <ul className="genui-proscons__list">
      {items.map((item, i) => (
        <li className="genui-proscons__item" key={`${tone}-${i}`}>
          <Mark tone={tone} />
          <div className="genui-proscons__text">
            <SafeMarkdown>{item}</SafeMarkdown>
          </div>
        </li>
      ))}
    </ul>
  </div>
);

const usable = (items: unknown): string[] =>
  Array.isArray(items)
    ? items.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
    : [];

export const ProsCons: React.FC<ProsConsProps> = ({ data, className = '' }) => {
  const { title, prosHeading, consHeading, pros, cons } = data;

  const proItems = usable(pros);
  const conItems = usable(cons);

  if (proItems.length === 0 && conItems.length === 0) return null;

  const single = proItems.length === 0 || conItems.length === 0;
  const gridClass = `genui-proscons__cols ${single ? 'genui-proscons__cols--single' : ''}`.trim();

  return (
    <section className={`genui-proscons ${className}`.trim()}>
      {title && <h2 className="genui-proscons__title">{title}</h2>}
      <div className={gridClass}>
        {proItems.length > 0 && (
          <Column heading={prosHeading || 'Pros'} items={proItems} tone="pro" />
        )}
        {conItems.length > 0 && (
          <Column heading={consHeading || 'Cons'} items={conItems} tone="con" />
        )}
      </div>
    </section>
  );
};

export default ProsCons;
