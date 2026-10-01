/**
 * ComponentRenderer
 * Dynamically renders GenUI components based on their type
 */

import React from 'react';
import type {
  GenUIComponent,
  TextComponentData,
  BentoComponentData,
  ChartComponentData,
  ButtonsComponentData
} from '../types';
import { TextComponent } from './TextComponent';
import { BentoComponent } from './BentoComponent';
import { ChartComponent } from './ChartComponent';
import { ButtonsComponent } from './ButtonsComponent';
import { TabsFeature } from './TabsFeature';
import { StepsSection } from './StepsSection';
import { StatsBanner } from './StatsBanner';
import { TestimonialCarousel } from './TestimonialCarousel';
import { PricingCards } from './PricingCards';
import { ContentGrid } from './ContentGrid';
import { HeroBanner } from './HeroBanner';
import { CaseStudies } from './CaseStudies';
import { ComparisonBars } from './ComparisonBars';
import { MetricsTrend } from './MetricsTrend';
import { Faq } from './Faq';
import { ProsCons } from './ProsCons';
import { QuoteBlock } from './QuoteBlock';
import { LogoWall } from './LogoWall';
import { ComponentErrorBoundary } from './ErrorBoundary';
import { getRegisteredGenUIComponent, BUILTIN_TYPES } from '../registry';

export interface ComponentRendererProps {
  component?: GenUIComponent;
  components?: GenUIComponent[];
  className?: string;
}

const toCamelCase = (str: string): string => {
  return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
};

export const normalizeData = (data: any): any => {
  if (data === null || data === undefined) return data;

  if (Array.isArray(data)) {
    return data.map(item => normalizeData(item));
  }

  // Object.entries, never a method looked up on the payload: in model output "hasOwnProperty" is just another key.
  if (typeof data === 'object') {
    const normalized: any = {};
    for (const [key, value] of Object.entries(data)) {
      normalized[toCamelCase(key)] =
        key === 'metadata' ? value : normalizeData(value);
    }
    return normalized;
  }

  return data;
};

/**
 * Normalization and dispatch run here, inside the boundary: anything the payload makes throw costs this component only.
 */
const ComponentBody: React.FC<{ component: GenUIComponent }> = ({ component }) => {
  const { type, layout } = component;
  const data = normalizeData(component.data);

  // A host registration wins over the framework's own component of the same name.
  const RegisteredComponent = getRegisteredGenUIComponent(type);
  if (RegisteredComponent) {
    return (
      <RegisteredComponent
        data={BUILTIN_TYPES.includes(type) ? data : component.data}
        layout={layout}
      />
    );
  }

  switch (type) {
    case 'text':
      return <TextComponent data={data as TextComponentData} />;

    case 'bento':
      return <BentoComponent data={data as BentoComponentData} />;

    case 'chart':
      return <ChartComponent data={data as ChartComponentData} />;

    case 'buttons':
      return <ButtonsComponent data={data as ButtonsComponentData} />;

    case 'tabs_feature':
      return <TabsFeature data={data} />;

    case 'steps_section':
      return <StepsSection data={data} />;

    case 'stats_banner':
      return <StatsBanner data={data} />;

    case 'testimonial_carousel':
      return <TestimonialCarousel data={data} />;

    case 'pricing_cards':
      return <PricingCards data={data} />;

    case 'content_grid':
      return <ContentGrid data={data} />;

    case 'hero_banner':
      return <HeroBanner data={data} />;

    case 'case_studies':
      return <CaseStudies data={data} />;

    case 'comparison_bars':
      return <ComparisonBars data={data} />;

    case 'metrics_trend':
      return <MetricsTrend data={data} />;

    case 'faq':
      return <Faq data={data} />;

    case 'pros_cons':
      return <ProsCons data={data} />;

    case 'quote':
      return <QuoteBlock data={data} />;

    case 'logo_wall':
      return <LogoWall data={data} />;

    default: {
      console.warn(
        `GenUI: unknown component type "${type}" (newer backend contract?), skipping`
      );
      if (
        typeof process !== 'undefined' &&
        process.env &&
        process.env.NODE_ENV !== 'production'
      ) {
        return (
          <div className="genui-error">
            Unknown component type: {type}
          </div>
        );
      }
      return null;
    }
  }
};

const renderSingleComponent = (
  component: GenUIComponent,
  index: number
): React.ReactNode => {
  const { type, layout } = component;

  // A component with no data object can't render anything useful and would throw downstream (.map/.split on undefined), so skip it quietly.
  if (component.data == null || typeof component.data !== 'object') {
    if (!getRegisteredGenUIComponent(type)) {
      console.warn(`GenUI: component "${type}" has no data, skipping`);
      return null;
    }
  }

  const wrapperStyle: React.CSSProperties = layout ? {
    width: layout.width,
    maxWidth: layout.maxWidth,
    margin: layout.margin,
    padding: layout.padding,
  } : {};

  const key = `genui-component-${type}-${index}`;

  // Isolate each component: a render-time throw must not take down the
  // sibling components, or the host application.
  const guarded = (
    <ComponentErrorBoundary label={type} resetKey={component}>
      <ComponentBody component={component} />
    </ComponentErrorBoundary>
  );

  if (Object.keys(wrapperStyle).length > 0) {
    return (
      <div key={key} style={wrapperStyle}>
        {guarded}
      </div>
    );
  }

  return <React.Fragment key={key}>{guarded}</React.Fragment>;
};

export const ComponentRenderer: React.FC<ComponentRendererProps> = ({
  component,
  components,
  className = '',
}) => {
  if (component && !components) {
    return <>{renderSingleComponent(component, 0)}</>;
  }

  if (components && components.length > 0) {
    return (
      <div className={`genui-components ${className}`.trim()}>
        {components.map((comp, index) => renderSingleComponent(comp, index))}
      </div>
    );
  }

  // Nothing to render
  return null;
};

export default ComponentRenderer;
