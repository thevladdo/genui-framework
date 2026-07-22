/**
 * ContentGrid: blog/news card grid.
 *
 * Per-item layout: "with-image" (16:9 thumbnail on top) or "text-only"
 * (accent top rail + colored category: the card is DESIGNED without an
 * image, not an image card with a hole). An item whose imageUrl is
 * missing or unsafe silently renders the text-only shape.
 */

import React from 'react';
import type { ContentGridData, ContentGridItem } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface ContentGridProps {
  data: ContentGridData;
  className?: string;
}

const Card: React.FC<{ item: ContentGridItem }> = ({ item }) => {
  const imageUrl =
    item.layout === 'with-image' ? sanitizeUrl(item.imageUrl) : undefined;
  const href = sanitizeUrl(item.url);

  const body = (
    <>
      {imageUrl && (
        <img className="genui-contentgrid__thumb" src={imageUrl} alt="" />
      )}
      <div className="genui-contentgrid__body">
        {item.category && (
          <span className="genui-contentgrid__category">{item.category}</span>
        )}
        <h3 className="genui-contentgrid__title">{item.title}</h3>
        {item.excerpt && (
          <p className="genui-contentgrid__excerpt">{item.excerpt}</p>
        )}
        {item.date && <span className="genui-contentgrid__date">{item.date}</span>}
      </div>
    </>
  );

  const cardClass = `genui-contentgrid__card ${imageUrl ? '' : 'genui-contentgrid__card--text-only'
    }`.trim();

  if (href) {
    return (
      <a className={cardClass} href={href}>
        {body}
      </a>
    );
  }
  return <article className={cardClass}>{body}</article>;
};

export const ContentGrid: React.FC<ContentGridProps> = ({ data, className = '' }) => {
  const { items, columns = 3 } = data;

  if (!Array.isArray(items) || items.length === 0) return null;

  const cols = Math.max(1, Math.min(columns, 4, items.length));

  return (
    <section
      className={`genui-contentgrid ${className}`.trim()}
      style={{ ['--genui-content-cols' as string]: cols }}
    >
      {items.map((item, i) => (
        <Card key={`${item.title}-${i}`} item={item} />
      ))}
    </section>
  );
};

export default ContentGrid;
