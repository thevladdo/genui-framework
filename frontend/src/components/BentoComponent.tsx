/**
 * BentoComponent
 * Dark glassmorphism bento grid with motion effects
 */

import React from "react";
import { motion } from "framer-motion";
import type { BentoComponentData, BentoCard } from "../types";

export interface BentoComponentProps {
  data: BentoComponentData;
  className?: string;
}

interface CardProps {
  card: BentoCard;
  index: number;
}

const Card: React.FC<CardProps> = ({ card, index }) => {
  const { title, description, link, image, badge } = card;

  const getGridAreaClass = (idx: number): string => {
    const areas = [
      "polo",
      "secondary1",
      "secondary2",
      "tertiary1",
      "tertiary2",
      "tertiary3",
    ];
    return areas[idx] || "";
  };

  const content = (
    <>
      {image && (
        <div
          className="genui-bento-card__bg"
          style={{ backgroundImage: `url(${image})` }}
        />
      )}

      <div className="genui-bento-card__overlay" />

      {badge && <span className="genui-bento-card__badge">{badge}</span>}

      <div className="genui-bento-card__content">
        <h3 className="genui-bento-card__title">{title}</h3>
        {description && (
          <p className="genui-bento-card__description">{description}</p>
        )}
      </div>
    </>
  );

  const motionProps = {
    initial: { scale: 1 },
    whileHover: { scale: 1.02 },
    transition: { duration: 0.3, ease: [0.4, 0, 0.2, 1] as const },
  };

  const gridArea = getGridAreaClass(index);
  const style: React.CSSProperties = gridArea ? { gridArea } : {};

  if (link) {
    return (
      <motion.a
        href={link}
        className="genui-bento-card"
        target="_blank"
        rel="noopener noreferrer"
        style={style}
        {...motionProps}
      >
        {content}
      </motion.a>
    );
  }

  return (
    <motion.div className="genui-bento-card" style={style} {...motionProps}>
      {content}
    </motion.div>
  );
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
        <Card key={`${card.title}-${index}`} card={card} index={index} />
      ))}
    </div>
  );
};

export default BentoComponent;
