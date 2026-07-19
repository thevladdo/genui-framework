/**
 * ChartComponent (lazy shell)
 *
 * Recharts is most of the library's bundle weight and most zones never
 * render a chart, so the real implementation (ChartComponentImpl) is
 * loaded on demand via React.lazy. The Suspense boundary lives here so
 * the public API is unchanged: <ChartComponent /> keeps working exactly
 * as before, no wrapper required in the host app. Server-side rendering
 * emits the skeleton fallback.
 */

import React, { Suspense } from 'react';
import type { ChartComponentProps } from './ChartComponentImpl';

const LazyChart = React.lazy(() => import('./ChartComponentImpl'));

export type { ChartComponentProps };

export const ChartComponent: React.FC<ChartComponentProps> = (props) => (
  <Suspense
    fallback={
      <div className="genui-zone-skeleton">
        <div className="genui-zone-skeleton__block" />
      </div>
    }
  >
    <LazyChart {...props} />
  </Suspense>
);

export default ChartComponent;
