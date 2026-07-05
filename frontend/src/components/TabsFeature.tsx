/**
 * TabsFeature: tabbed feature section (plans comparison, SaaS highlights,
 * product categories).
 *
 * Tab state is a plain useState: three-to-five tabs don't justify a
 * dependency. Each tab's content declares layout "with-image" | "text-only";
 * text-only panels change shape (single centered column, larger title)
 * instead of leaving an image-shaped hole.
 */

import React, { useState } from 'react';
import type { TabsFeatureData } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface TabsFeatureProps {
  data: TabsFeatureData;
  className?: string;
}

export const TabsFeature: React.FC<TabsFeatureProps> = ({ data, className = '' }) => {
  const { badge, heading, description, tabs } = data;
  const [active, setActive] = useState(0);

  if (!Array.isArray(tabs) || tabs.length === 0) return null;

  const tab = tabs[Math.min(active, tabs.length - 1)];
  const content = tab.content ?? { layout: 'text-only' as const, title: tab.label };
  const imageUrl = content.layout === 'with-image' ? sanitizeUrl(content.imageUrl) : undefined;
  const buttonUrl = sanitizeUrl(content.button?.url);
  const textOnly = !imageUrl;

  return (
    <section className={`genui-tabsfeature ${className}`.trim()}>
      <header className="genui-tabsfeature__header">
        {badge && <span className="genui-tabsfeature__badge">{badge}</span>}
        <h2 className="genui-tabsfeature__heading">{heading}</h2>
        {description && <p className="genui-tabsfeature__description">{description}</p>}
      </header>

      {tabs.length > 1 && (
        <div className="genui-tabsfeature__triggers" role="tablist">
          {tabs.map((t, i) => (
            <button
              key={`${t.label}-${i}`}
              type="button"
              role="tab"
              aria-selected={i === active}
              className="genui-tabsfeature__trigger"
              onClick={() => setActive(i)}
            >
              {t.icon && <span aria-hidden="true">{t.icon}</span>}
              {t.label}
            </button>
          ))}
        </div>
      )}

      <div
        role="tabpanel"
        className={`genui-tabpanel ${textOnly ? 'genui-tabpanel--text-only' : ''}`.trim()}
      >
        <div className="genui-tabpanel__body">
          {content.badge && <span className="genui-tabpanel__badge">{content.badge}</span>}
          <h3 className="genui-tabpanel__title">{content.title}</h3>
          {content.description && (
            <p className="genui-tabpanel__description">{content.description}</p>
          )}
          {content.button?.label && buttonUrl && (
            <a className="genui-hero__cta" href={buttonUrl}>
              {content.button.label}
            </a>
          )}
        </div>
        {imageUrl && (
          <img className="genui-tabpanel__image" src={imageUrl} alt={content.title} />
        )}
      </div>
    </section>
  );
};

export default TabsFeature;
