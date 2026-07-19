/**
 * BentoComponent
 * Dark glassmorphism bento grid with motion effects
 */

import React from "react";
import type { BentoComponentData, BentoCard } from "../types";
import { sanitizeUrl } from "../utils/sanitizeUrl";

export interface BentoComponentProps {
  data: BentoComponentData;
  className?: string;
}

interface CardProps {
  card: BentoCard;
}

const Card: React.FC<CardProps> = ({ card }) => {
  const { title, description, badge, action } = card;
  const link = sanitizeUrl(card.link);
  const image = sanitizeUrl(card.image);
  const actionHref = sanitizeUrl(action?.url);
  const hasAction = Boolean(action && (actionHref || action.onClick));

  const content = (
    <>
      {image && (
        <div
          className="genui-bento-card__bg"
          style={{ backgroundImage: `url(${image})` }}
        />
      )}

      {/* Readability gradient: only meaningful over a photo */}
      {image && <div className="genui-bento-card__overlay" />}

      {badge && <span className="genui-bento-card__badge">{badge}</span>}

      <div className="genui-bento-card__content">
        <h3 className="genui-bento-card__title">{title}</h3>
        {description && (
          <p className="genui-bento-card__description">{description}</p>
        )}
        {hasAction &&
          (actionHref ? (
            <a
              href={actionHref}
              className="genui-bento-card__action"
              target="_blank"
              rel="noopener noreferrer"
            >
              {action!.label}
            </a>
          ) : (
            <button
              type="button"
              className="genui-bento-card__action"
              onClick={action!.onClick}
            >
              {action!.label}
            </button>
          ))}
      </div>
    </>
  );

  // The default grid flows cards into the N-column layout
  // (genui-bento--cols-*). The named-area "complex" layout is opt-in via
  // the .genui-layout-complex class and assigned purely in CSS (nth-child),
  // so no inline grid-area is applied here. Applying one unconditionally
  // would collapse every card into the same cell in the simple layout.
  // Image-optional degradation: without a cover the card gets an
  // accent-tinted gradient (CSS) instead of an empty dark box
  const cardClass = `genui-bento-card ${image ? '' : 'genui-bento-card--text-only'}`.trim();

  if (link && !hasAction) {
    return (
      <a
        href={link}
        className={cardClass}
        target="_blank"
        rel="noopener noreferrer"
      >
        {content}
      </a>
    );
  }

  return <div className={cardClass}>{content}</div>;
};

export const BentoComponent: React.FC<BentoComponentProps> = ({
  data,
  className = "",
}) => {
  const { cards, columns = 3, gap } = data;

  const colClass =
    `genui-bento genui-bento--cols-${columns} ${className}`.trim();

  const style: React.CSSProperties = gap ? { gap: `${gap}px` } : {};

  return (
    <div className={colClass} style={style}>
      {cards.map((card, index) => (
        <Card key={`${card.title}-${index}`} card={card} />
      ))}
    </div>
  );
};

export default BentoComponent;
