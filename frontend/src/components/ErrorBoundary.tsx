/**
 * ComponentErrorBoundary
 *
 * GenUI renders LLM-generated content, so a malformed component must
 * never crash the host application. This boundary isolates each rendered
 * component: if one throws during render, only that component is replaced
 * with a quiet fallback: the rest of the zone, and the host app around
 * it, keep working.
 *
 * Error boundaries must be class components (no hook equivalent exists).
 */

import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Rendered instead of the crashed component (default: nothing) */
  fallback?: React.ReactNode;
  /** Identifier included in the console warning, e.g. the component type */
  label?: string;
  /** Notified when a child throws */
  onError?: (error: Error) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ComponentErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error): void {
    console.warn(
      `GenUI: component${this.props.label ? ` "${this.props.label}"` : ''} failed to render`,
      error
    );
    this.props.onError?.(error);
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      return this.props.fallback ?? null;
    }
    return this.props.children;
  }
}

export default ComponentErrorBoundary;
