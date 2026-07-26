/**
 * Content policy editor.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import studioStyles from '../studio/Studio.module.css';
import previewStyles from '../preview/Preview.module.css';
import styles from './Policy.module.css';
import {
  getContentPolicy,
  saveContentPolicy,
  type ContentPolicyResponse,
} from '../../lib/api';
import { getSession, sessionId, type AdminSession } from '../../lib/session';
import { ConnectGate } from '../studio/ConnectGate';
import { ConsoleHeader } from '../studio/ConsoleHeader';

const parseTerms = (text: string): string[] => {
  const seen = new Map<string, null>();
  for (const line of text.split('\n')) {
    const term = line.trim();
    if (term) seen.set(term, null);
  }
  return [...seen.keys()];
};

const EnforceExplainer = () => (
  <div className={styles.enforceGrid}>
    <div className={styles.enforceCard}>
      <span className={styles.badge}>Enforced</span>
      <p>
        Banned terms are matched on the output and removed: a component
        containing one is dropped whole, chat prose has it redacted, and
        every hit is reported in <code>meta.sanitization.policy_violations</code>.
        Matching is case-insensitive, word-boundary and phrase-aware.
      </p>
    </div>
    <div className={`${styles.enforceCard} ${styles.enforceCardMuted}`}>
      <span className={`${styles.badge} ${styles.badgeMuted}`}>Best-effort, not guaranteed</span>
      <p>
        Matching is lexical, not semantic: misspellings, synonyms and
        paraphrases are not caught. The guarantee is “this exact term never
        appears”, not “this topic never appears”. Tone (“formal”, “no
        superlatives”) stays a prompt-level instruction, and cannot be
        enforced here.
      </p>
    </div>
  </div>
);

const PolicyEditor = ({ session }: { session: AdminSession }) => {
  const [policy, setPolicy] = useState<ContentPolicyResponse | null>(null);
  const [termsText, setTermsText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [envOpen, setEnvOpen] = useState(false);
  const envPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!envOpen) return;
    envPanelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setEnvOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [envOpen]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const loaded = await getContentPolicy(session);
      setPolicy(loaded);
      setTermsText(loaded.banned_terms.join('\n'));
      setNotice(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the content policy');
    }
  }, [session]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const terms = parseTerms(termsText);
      const before = policy?.banned_terms ?? [];
      const saved = await saveContentPolicy(session, terms);
      setPolicy(saved);
      setTermsText(saved.banned_terms.join('\n'));

      const after = saved.banned_terms;
      const removed = before.filter((t) => !after.includes(t)).length;
      const enforcedTail =
        ' Enforced on the next render of every zone and every chat answer for this tenant.';
      const memoryWarning =
        saved.storage === 'memory'
          ? ' WARNING: Redis is unreachable, this policy lives in one worker\'s memory and is lost on restart.'
          : '';

      let summary: string;
      if (after.length === 0) {
        summary =
          'Cleared. This tenant now has no banned terms of its own; only the deployment-wide env terms (if any) still apply.';
      } else if (removed > 0) {
        summary =
          `Removed ${removed} term${removed === 1 ? '' : 's'}, ${after.length} still saved.` + enforcedTail;
      } else {
        summary =
          `Saved ${after.length} banned term${after.length === 1 ? '' : 's'}.` + enforcedTail;
      }
      setNotice(summary + memoryWarning);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const envTerms = policy?.env_terms ?? [];

  return (
    <section className={`st-glass ${studioStyles.testerCard}`}>
      <h2 className="st-section-title">Banned terms</h2>

      {policy?.storage === 'memory' && (
        <p className={previewStyles.warnBanner} role="alert">
          Redis is unreachable: the policy is currently stored in one
          worker's memory and will be LOST on restart. Fix the backend's
          Redis connection before relying on it.
        </p>
      )}

      <EnforceExplainer />

      <div className={styles.labelRow}>
        <label className={studioStyles.fieldLabel} htmlFor="cp-terms">
          Banned terms for this tenant (one per line)
        </label>
        <button
          type="button"
          className={styles.envPill}
          aria-haspopup="dialog"
          aria-expanded={envOpen}
          onClick={() => setEnvOpen(true)}
        >
          Deployment terms ({envTerms.length})
        </button>
      </div>
      <textarea
        id="cp-terms"
        className={styles.termsArea}
        value={termsText}
        onChange={(e) => setTermsText(e.target.value)}
        placeholder={'guaranteed returns\nfree money\nrisk-free'}
        spellCheck={false}
      />

      <div className={styles.actionsRow}>
        <button
          type="button"
          className={studioStyles.primaryButton}
          disabled={busy}
          onClick={() => void save()}
        >
          Save policy
        </button>
      </div>

      {error && <p className={studioStyles.error} role="alert">{error}</p>}
      {notice && <p className={styles.notice}>{notice}</p>}

      {envOpen && (
        <div className={styles.overlay} onClick={() => setEnvOpen(false)}>
          <div
            ref={envPanelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cp-env-title"
            tabIndex={-1}
            className={`st-glass ${styles.panel}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.modalHead}>
              <h3 id="cp-env-title" className={styles.modalTitle}>Deployment-wide terms</h3>
              <button
                type="button"
                className={styles.modalClose}
                aria-label="Close"
                onClick={() => setEnvOpen(false)}
              >
                ×
              </button>
            </div>
            <p className={styles.modalSub}>
              Enforced for this tenant via the backend env (<code>CONTENT_POLICY</code>),
              set by whoever runs the deployment. Read-only here.
            </p>
            {envTerms.length > 0 ? (
              <div className={styles.envTerms}>
                {envTerms.map((term) => (
                  <span key={term} className={styles.termChip}>{term}</span>
                ))}
              </div>
            ) : (
              <p className={styles.modalEmpty}>No deployment-wide terms are configured.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

const PolicyWorkbench = ({
  session,
  onSession,
}: {
  session: AdminSession;
  onSession: (next: AdminSession | null) => void;
}) => (
  <main className={studioStyles.page} style={{ marginTop: '3rem' }}>
    <ConsoleHeader session={session} onSession={onSession} />

    <PolicyEditor session={session} />
  </main>
);

export const PolicyPage = () => {
  const [session, setSession] = useState<AdminSession | null>(() => getSession());

  if (!session) {
    return <ConnectGate onConnected={setSession} />;
  }

  return (
    <PolicyWorkbench
      key={sessionId(session)}
      session={session}
      onSession={setSession}
    />
  );
};

export default PolicyPage;
