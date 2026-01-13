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

      default:
        console.warn(`Unknown component type: ${type}`);
        return (
          <div className="genui-error">
            Unknown component type: {type}
          </div>
        );
    }
  };

  if (Object.keys(wrapperStyle).length > 0) {
    return (
      <div key={key} style={wrapperStyle}>
        {renderComponent()}
      </div>
    );
  }

  return <React.Fragment key={key}>{renderComponent()}</React.Fragment>;
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
