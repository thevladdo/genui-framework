/**
 * ChartComponent
 * Various chart types using Recharts
 */

import React from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { ChartComponentData, ChartDataPoint } from '../types';

export interface ChartComponentProps {
  data: ChartComponentData;
  className?: string;
}

// Default color palette
const COLORS = [
  '#3b82f6',
  '#22c55e',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#f97316',
];

const getColor = (index: number, dataPoint?: ChartDataPoint): string => {
  return dataPoint?.color || COLORS[index % COLORS.length];
};

export const ChartComponent: React.FC<ChartComponentProps> = ({
  data,
  className = ''
}) => {
  const {
    chartType,
    title,
    data: chartData,
    xAxis,
    yAxis,
    showLegend,
    showGrid = true,
    height = 300,
  } = data;

  // Transform data for Recharts format
  const formattedData = chartData.map((item, index) => ({
    name: item.label,
    value: item.value,
    fill: getColor(index, item),
  }));

  const renderChart = () => {
    const commonProps = {
      data: formattedData,
    };

    switch (chartType) {
      case 'bar':
        return (
          <BarChart {...commonProps}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" />}
            <XAxis dataKey="name" label={xAxis ? { value: xAxis, position: 'bottom' } : undefined} />
            <YAxis label={yAxis ? { value: yAxis, angle: -90, position: 'left' } : undefined} />
            <Tooltip />
            {showLegend && <Legend />}
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {formattedData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        );

      case 'line':
        return (
          <LineChart {...commonProps}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" />}
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            {showLegend && <Legend />}
            <Line
              type="monotone"
              dataKey="value"
              stroke={COLORS[0]}
              strokeWidth={2}
              dot={{ fill: COLORS[0] }}
            />
          </LineChart>
        );

      case 'area':
        return (
          <AreaChart {...commonProps}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" />}
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            {showLegend && <Legend />}
            <Area
              type="monotone"
              dataKey="value"
              stroke={COLORS[0]}
              fill={COLORS[0]}
              fillOpacity={0.3}
            />
          </AreaChart>
        );

      case 'pie':
      case 'donut':
        return (
          <PieChart>
            <Pie
              data={formattedData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={chartType === 'donut' ? 60 : 0}
              outerRadius={100}
              paddingAngle={chartType === 'donut' ? 2 : 0}
              label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            >
              {formattedData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip />
            {(showLegend ?? true) && <Legend />}
          </PieChart>
        );

      default:
        return (
          <div className="genui-error">
            Unknown chart type: {chartType}
          </div>
        );
    }
  };

  return (
    <div className={`genui-chart ${className}`.trim()}>
      {title && <h3 className="genui-chart__title">{title}</h3>}
      <div className="genui-chart__container" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {renderChart()}
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default ChartComponent;
