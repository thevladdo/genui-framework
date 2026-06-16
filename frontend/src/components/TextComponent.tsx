/**
 * TextComponent
 * Renders markdown content via react-markdown.
 *
 * Uses the bundled react-markdown instead of a hand-rolled parser so that
 * headings, lists, nested emphasis, code and links all render correctly.
 * Link URLs pass through sanitizeUrl (urlTransform), so a markdown link
 * with a dangerous scheme is stripped — defense-in-depth matching the
 * URL whitelist applied to every other component.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { TextComponentData } from '../types';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface TextComponentProps {
  data: TextComponentData;
  className?: string;
}

export const TextComponent: React.FC<TextComponentProps> = ({
  data,
  className = ''
}) => {
  const { content, style = 'normal' } = data;

  // Tolerate a missing content string (would otherwise be a render error)
  const safeContent = typeof content === 'string' ? content : '';
  if (!safeContent.trim()) {
    return null;
  }

  const wrapperClass = `genui-text genui-text--${style} ${className}`.trim();

  return (
    <div className={wrapperClass}>
      <ReactMarkdown
        // Strip dangerous/non-allowed URLs from links and images
        urlTransform={(url) => sanitizeUrl(url) ?? ''}
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {safeContent}
      </ReactMarkdown>
    </div>
  );
};

export default TextComponent;
