/**
 * Every component that renders model-authored markdown goes through here.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { sanitizeUrl } from '../utils/sanitizeUrl';

export interface SafeMarkdownProps {
  children: string;
}

export const SafeMarkdown: React.FC<SafeMarkdownProps> = ({ children }) => (
  <ReactMarkdown
    urlTransform={(url) => sanitizeUrl(url) ?? ''}
    components={{
      a: ({ children: linkChildren, ...props }) => (
        <a {...props} target="_blank" rel="noopener noreferrer">
          {linkChildren}
        </a>
      ),
    }}
  >
    {children}
  </ReactMarkdown>
);

export default SafeMarkdown;
