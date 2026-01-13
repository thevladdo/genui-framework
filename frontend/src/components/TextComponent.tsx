/**
 * TextComponent
 * Renders text content with various styling options and Markdown support
 */


import React from 'react';
import type { TextComponentData } from '../types';

export interface TextComponentProps {
  data: TextComponentData;
  className?: string;
}

const parseMarkdown = (text: string): JSX.Element => {
  const lines = text.split('\n');
  const elements: JSX.Element[] = [];

  lines.forEach((line, idx) => {
    const listMatch = line.match(/^(\d+)\.\s+\*\*(.*?)\*\*:\s*(.*)/);
    if (listMatch) {
      const [, num, title, description] = listMatch;
      elements.push(
        <div key={idx} style={{ marginBottom: '12px' }}>
          <strong>{num}. {title}:</strong> {parseInlineMarkdown(description)}
        </div>
      );
      return;
    }

    if (line.trim()) {
      elements.push(
        <span key={idx}>
          {parseInlineMarkdown(line)}
          {idx < lines.length - 1 && <br />}
        </span>
      );
    } else if (idx < lines.length - 1) {
      elements.push(<br key={idx} />);
    }
  });

  return <>{elements}</>;
};

const parseInlineMarkdown = (text: string): React.ReactNode => {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    // Bold: **text**
    const boldMatch = remaining.match(/^\*\*(.*?)\*\*/);
    if (boldMatch) {
      parts.push(<strong key={key++}>{boldMatch[1]}</strong>);
      remaining = remaining.slice(boldMatch[0].length);
      continue;
    }

    // Italic: *text*
    const italicMatch = remaining.match(/^\*(.*?)\*/);
    if (italicMatch) {
      parts.push(<em key={key++}>{italicMatch[1]}</em>);
      remaining = remaining.slice(italicMatch[0].length);
      continue;
    }

    // Code: `text`
    const codeMatch = remaining.match(/^`(.*?)`/);
    if (codeMatch) {
      parts.push(<code key={key++} style={{
        backgroundColor: '#f3f4f6',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.9em'
      }}>{codeMatch[1]}</code>);
      remaining = remaining.slice(codeMatch[0].length);
      continue;
    }

    // Links: [text](url)
    const linkMatch = remaining.match(/^\[(.*?)\]\((.*?)\)/);
    if (linkMatch) {
      parts.push(
        <a
          key={key++}
          href={linkMatch[2]}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: 'var(--genui-accent-color)', textDecoration: 'underline' }}
        >
          {linkMatch[1]}
        </a>
      );
      remaining = remaining.slice(linkMatch[0].length);
      continue;
    }

    // Regular text - find next special character
    const nextSpecial = remaining.search(/[\*`\[]/);
    if (nextSpecial === -1) {
      parts.push(remaining);
      break;
    } else {
      parts.push(remaining.slice(0, nextSpecial));
      remaining = remaining.slice(nextSpecial);
    }
  }

  return <>{parts}</>;
};

export const TextComponent: React.FC<TextComponentProps> = ({
  data,
  className = ''
}) => {
  const { content, style = 'normal' } = data;

  const styleClass = `genui-text genui-text--${style} ${className}`.trim();

  const formattedContent = parseMarkdown(content);

  // Render different HTML elements based on style
  switch (style) {
    case 'heading':
      return <h2 className={styleClass}>{formattedContent}</h2>;
    case 'note':
      return <aside className={styleClass}>{formattedContent}</aside>;
    default:
      return <div className={styleClass}>{formattedContent}</div>;
  }
};

export default TextComponent;
