/**
 * Save panel: the three export formats plus the share link.
 */

import { useEffect, useRef, useState } from 'react';
import styles from './Playground.module.css';
import {
  exportAsCSS,
  exportAsJSON,
  exportAsTS,
  themeToQuery,
  type StudioTheme,
} from '../../lib/theme';

interface ExportPanelProps {
  theme: StudioTheme;
  onClose: () => void;
}

const shareUrl = (theme: StudioTheme): string => {
  const query = themeToQuery(theme);
  const base = `${window.location.origin}${window.location.pathname}#/playground`;
  return query ? `${base}?${query}` : base;
};

export const ExportPanel = ({ theme, onClose }: ExportPanelProps) => {
  const [copied, setCopied] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const copy = async (label: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(label);
    } catch {
      setCopied('error');
    }
  };

  const entries: Array<{ label: string; hint: string; content: string }> = [
    { label: 'TypeScript', hint: 'GenUITheme object', content: exportAsTS(theme) },
    { label: 'CSS variables', hint: ':root block', content: exportAsCSS(theme) },
    { label: 'JSON', hint: 'raw config', content: exportAsJSON(theme) },
    { label: 'Share link', hint: 'URL with this theme', content: shareUrl(theme) },
  ];

  return (
    <div className={styles.exportOverlay} onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Export theme"
        tabIndex={-1}
        className={`st-glass ${styles.exportPanel}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={styles.exportHeader}>
          <h2 className="st-section-title">Save theme</h2>
          <button type="button" onClick={onClose} className={styles.exportClose} aria-label="Close">
            ✕
          </button>
        </div>

        {entries.map((entry) => (
          <button
            key={entry.label}
            type="button"
            className={styles.exportRow}
            onClick={() => copy(entry.label, entry.content)}
          >
            <span>
              <span className={styles.exportLabel}>{entry.label}</span>
              <span className={styles.exportHint}>{entry.hint}</span>
            </span>
            <span className={styles.exportAction}>
              {copied === entry.label ? 'Copied ✓' : 'Copy'}
            </span>
          </button>
        ))}

        {copied === 'error' && (
          <p className={styles.exportError}>
            Clipboard unavailable: select and copy manually from the code below.
          </p>
        )}

        <pre className={styles.exportPreview}>
          <code>{exportAsTS(theme)}</code>
        </pre>
      </div>
    </div>
  );
};
