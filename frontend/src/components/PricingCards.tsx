/**
 * PricingCards: plan grid with optional "recommended" flag.
 *
 * variant "compact": cards only. variant "detailed": cards + a feature
 * comparison table built from the union of all plans' features (a
 * feature is ✓ for a plan when its features list contains it).
 */

import React from 'react';
import type { PricingCardsData, PricingPlan } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface PricingCardsProps {
  data: PricingCardsData;
  className?: string;
}

const Card: React.FC<{ plan: PricingPlan }> = ({ plan }) => {
  const ctaUrl = sanitizeUrl(plan.cta?.url);

  return (
    <article
      className={`genui-pricing__card ${plan.highlighted ? 'genui-pricing__card--highlighted' : ''
        }`.trim()}
    >
      {plan.highlighted && (
        <span className="genui-pricing__flag">{plan.flag ?? 'Recommended'}</span>
      )}
      <h3 className="genui-pricing__name">{plan.name}</h3>
      <p className="genui-pricing__price">
        {plan.price}
        {plan.period && <span className="genui-pricing__period"> /{plan.period}</span>}
      </p>
      {plan.description && <p className="genui-pricing__blurb">{plan.description}</p>}

      {(plan.features ?? []).length > 0 && (
        <ul className="genui-pricing__features">
          {(plan.features ?? []).map((feature, i) => (
            <li key={i} className="genui-pricing__feature">
              <span className="genui-pricing__check" aria-hidden="true">✓</span>
              {feature}
            </li>
          ))}
        </ul>
      )}

      {plan.cta?.label && ctaUrl && (
        <a className="genui-pricing__cta" href={ctaUrl}>
          {plan.cta.label}
        </a>
      )}
    </article>
  );
};

export const PricingCards: React.FC<PricingCardsProps> = ({ data, className = '' }) => {
  const { plans, variant = 'compact' } = data;

  if (!Array.isArray(plans) || plans.length === 0) return null;

  // Union of features, in first-seen order, for the comparison table.
  const allFeatures =
    variant === 'detailed' && plans.length > 1
      ? [...new Set(plans.flatMap((plan) => plan.features ?? []))]
      : [];

  return (
    <section className={`genui-pricing-wrap ${className}`.trim()}>
      <div
        className="genui-pricing"
        style={{ ['--genui-pricing-cols' as string]: Math.min(plans.length, 3) }}
      >
        {plans.map((plan, i) => (
          <Card key={`${plan.name}-${i}`} plan={plan} />
        ))}
      </div>

      {variant === 'detailed' && allFeatures.length > 0 && (
        <table className="genui-pricing__table">
          <thead>
            <tr>
              <th scope="col">Feature</th>
              {plans.map((plan, i) => (
                <th key={i} scope="col">{plan.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {allFeatures.map((feature) => (
              <tr key={feature}>
                <td>{feature}</td>
                {plans.map((plan, i) => (
                  <td key={i}>
                    {(plan.features ?? []).includes(feature) ? '✓' : '✕'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
};

export default PricingCards;
