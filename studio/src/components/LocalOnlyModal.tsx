/**
 * LocalOnlyModal
 *
 * Shown on the public (GitHub Pages) build when a visitor opens an admin
 * tool (Content Studio, Measurement dashboard): they need a reachable
 * backend + admin key, so they're gated to local dev until proper user
 * auth (JWT) lands. In dev this component is never rendered, the real
 * pages load instead.
 */

import { useEffect, useRef } from 'react';
import styles from './LocalOnlyModal.module.css';

interface LocalOnlyModalProps {
  onClose: () => void;
  title?: string;
  body?: string;
}

export const LocalOnlyModal = ({
  onClose,
  title = 'Content Studio runs locally',
  body = "The Content Studio manages your RAG knowledge base and it needs a reachable GenUI backend and an admin key, so for now it's available only when you run the studio on your own machine:",
}: LocalOnlyModalProps) => {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="local-only-title"
        tabIndex={-1}
        className={`st-glass ${styles.panel}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.icon} aria-hidden="true">🔒</div>
        <h2 id="local-only-title" className={styles.title}>
          {title}
        </h2>
        <p className={styles.body}>{body}</p>
        <pre className={styles.code}><code>cd studio &amp;&amp; npm run dev</code></pre>
        <p className={styles.note}>
          A hosted version arrives once user authentication (JWT) is in place.
          The Theme Playground, meanwhile, works fully here — no backend needed.
        </p>
        <div className={styles.actions}>
          <a href="#/playground" className={styles.primary} onClick={onClose}>
            Open Theme Playground →
          </a>
          <button type="button" className={styles.secondary} onClick={onClose}>
            Back to home
          </button>
        </div>
      </div>
    </div>
  );
};

export default LocalOnlyModal;
