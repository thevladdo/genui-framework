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
import { ComponentErrorBoundary } from './ErrorBoundary';
import { getRegisteredGenUIComponent } from '../registry';

export interface ComponentRendererProps {
  component?: GenUIComponent;
  components?: GenUIComponent[];
  className?: string;
}

const toCamelCase = (str: string): string => {
  return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
};

const normalizeData = (data: any): any => {
  if (data === null || data === undefined) return data;

  if (Array.isArray(data)) {
    return data.map(item => normalizeData(item));
  }

  if (typeof data === 'object') {
    const normalized: any = {};
    for (const key in data) {
      if (data.hasOwnProperty(key)) {
        const camelKey = toCamelCase(key);
        normalized[camelKey] = normalizeData(data[key]);
      }
    }
    return normalized;
  }

  return data;
};

const renderSingleComponent = (
  component: GenUIComponent,
  index: number
): React.ReactNode => {
  const { type, layout } = component;

  // A component with no data object can't render anything useful and
  // would throw downstream (.map/.split on undefined), so skip it quietly.
  if (component.data == null || typeof component.data !== 'object') {
    if (!getRegisteredGenUIComponent(type)) {
      console.warn(`GenUI: component "${type}" has no data, skipping`);
      return null;
    }
  }

  // Normalize data to ensure camelCase format
  const data = normalizeData(component.data);

  const wrapperStyle: React.CSSProperties = layout ? {
    width: layout.width,
    maxWidth: layout.maxWidth,
    margin: layout.margin,
    padding: layout.padding,
  } : {};

  const key = `genui-component-${type}-${index}`;

  const renderComponent = (): React.ReactNode => {
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

      default: {
        // Host-registered custom components (see registerGenUIComponent).
        // They receive the data exactly as validated against the host's
        // JSON schema: no snake_case -> camelCase normalization.
        const RegisteredComponent = getRegisteredGenUIComponent(type);
        if (RegisteredComponent) {
          return <RegisteredComponent data={component.data} layout={layout} />;
        }

        console.warn(`Unknown component type: ${type}`);
        return (
          <div className="genui-error">
            Unknown component type: {type}
          </div>
        );
      }
    }
  };

  // Isolate each component: a render-time throw must not take down the
  // sibling components, or the host application.
  const guarded = (
    <ComponentErrorBoundary label={type}>
      {renderComponent()}
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
