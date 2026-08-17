/**
 * The two moments where indexing with context stops being automatic and becomes a decision.
 */

import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import styles from './CorpusModals.module.css';

const PUBLISHED_SOURCE =
  'Measured on other corpora by the authors of the technique, not a prediction for this one.';

const formatNumber = (value: number): string => value.toLocaleString('en-US');

/** Share of the hourly cap, only when a cap exists. */
const budgetFigure = (calls: number, budgetPerHour: number | null) =>
  budgetPerHour
    ? { value: `${Math.round((calls / budgetPerHour) * 100)}%`, label: 'of the hourly cap' }
    : { value: 'None set', label: 'hourly cap' };

const Dialog = ({
  labelledBy,
  onDismiss,
  dismissable = true,
  children,
}: {
  labelledBy: string;
  onDismiss: () => void;
  dismissable?: boolean;
  children: ReactNode;
}) => {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && dismissable) onDismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onDismiss, dismissable]);

  return createPortal(
    <div className={styles.overlay} onClick={dismissable ? onDismiss : undefined}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={styles.panel}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
};

const Figures = ({
  items,
}: {
  items: { value: string; label: string }[];
}) => (
  <div className={styles.figures}>
    {items.map((item) => (
      <div key={item.label} className={styles.figure}>
        <span className={styles.figureValue}>{item.value}</span>
        <span className={styles.figureLabel}>{item.label}</span>
      </div>
    ))}
  </div>
);

interface SpendConfirmProps {
  chunks: number;
  calls: number;
  budgetPerHour: number | null;
  promptCache: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export const SpendConfirm = ({
  chunks,
  calls,
  budgetPerHour,
  promptCache,
  onConfirm,
  onCancel,
}: SpendConfirmProps) => (
  <Dialog labelledBy="spend-title" onDismiss={onCancel}>
    <span className={styles.eyebrow}>Before this upload starts</span>
    <h2 id="spend-title" className={styles.title}>
      This takes the knowledge base over the size where context pays
    </h2>
    <p className={styles.lede}>
      Every chunk gets a line or two placing it in its document, written by the
      model. It happens once, now, and nothing is indexed until it is done.
    </p>

    <Figures
      items={[
        { value: formatNumber(chunks), label: 'chunks to index' },
        { value: formatNumber(calls), label: 'model calls' },
        budgetFigure(calls, budgetPerHour),
      ]}
    />

    {promptCache === 'prefix' && (
      <p className={styles.note}>
        This engine has no explicit prompt cache: the document is sent with every
        call and billed again unless the endpoint reuses identical prefixes on
        its own.
      </p>
    )}

    <div className={styles.actions}>
      <button type="button" className={styles.primary} onClick={onConfirm}>
        Index with context
      </button>
      <button type="button" className={styles.secondary} onClick={onCancel}>
        Cancel the upload
      </button>
    </div>
  </Dialog>
);

interface BackfillDialogProps {
  estimate: { chunksPlain: number; calls: number; promptCache: string | null } | null;
  budgetPerHour: number | null;
  running: boolean;
  remaining: number | null;
  error: string | null;
  onStart: () => void;
  onStop?: () => void;
  onClose: () => void;
}

export const BackfillDialog = ({
  estimate,
  budgetPerHour,
  running,
  remaining,
  error,
  onStart,
  onStop,
  onClose,
}: BackfillDialogProps) => (
  <Dialog labelledBy="backfill-title" onDismiss={onClose} dismissable={!running}>
    <span className={styles.eyebrow}>Uneven retrieval</span>
    <h2 id="backfill-title" className={styles.title}>
      Bring the older chunks up to date
    </h2>
    <p className={styles.lede}>
      They were indexed before this knowledge base reached the size where
      context pays, so they compete against newer chunks without the lines that
      place them in their document. One run puts every passage back on the same
      terms.
    </p>

    {estimate === null && !running && (
      <p className={styles.note}>Working out what this costs, before spending anything…</p>
    )}

    {estimate && (
      <Figures
        items={[
          { value: formatNumber(estimate.chunksPlain), label: 'chunks without context' },
          { value: formatNumber(estimate.calls), label: 'model calls' },
          budgetFigure(estimate.calls, budgetPerHour),
        ]}
      />
    )}

    {running && (
      <p className={styles.note}>
        Working through them. It goes in runs, and each one picks up where the
        last stopped, so closing this later costs nothing already paid for.
        {remaining !== null && (
          <> <strong>{formatNumber(remaining)}</strong> left.</>
        )}
      </p>
    )}

    {estimate && estimate.promptCache === 'prefix' && !running && (
      <p className={styles.note}>
        This engine has no explicit prompt cache: each document is sent with
        every call about it and billed again unless the endpoint reuses
        identical prefixes on its own.
      </p>
    )}

    {error && <p className={styles.error} role="alert">{error}</p>}

    <div className={styles.actions}>
      <button
        type="button"
        className={styles.primary}
        onClick={onStart}
        disabled={running || estimate === null}
      >
        {running ? 'Working…' : 'Start'}
      </button>
      {running && onStop ? (
        <button type="button" className={styles.secondary} onClick={onStop}>
          Stop after this batch
        </button>
      ) : (
        <button
          type="button"
          className={styles.secondary}
          onClick={onClose}
          disabled={running}
        >
          Not now
        </button>
      )}
    </div>
  </Dialog>
);

interface CorpusDecisionProps {
  chunksLeftBehind: number;
  calls: number;
  budgetPerHour: number | null;
  busy: boolean;
  error: string | null;
  onBackfill: () => void;
  onOnlyNew: () => void;
  onLater: () => void;
}

export const CorpusDecision = ({
  chunksLeftBehind,
  calls,
  budgetPerHour,
  busy,
  error,
  onBackfill,
  onOnlyNew,
  onLater,
}: CorpusDecisionProps) => (
  <Dialog labelledBy="corpus-title" onDismiss={onLater} dismissable={!busy}>
    <span className={styles.eyebrow}>The knowledge base crossed the threshold</span>
    <h2 id="corpus-title" className={styles.title}>
      What should happen to the documents indexed before it?
    </h2>
    <p className={styles.lede}>
      New chunks now carry the lines that place them in their document. The older
      ones do not, and the two do not compete on equal terms.
    </p>

    <Figures
      items={[
        { value: formatNumber(chunksLeftBehind), label: 'chunks without context' },
        { value: formatNumber(calls), label: 'model calls' },
        budgetFigure(calls, budgetPerHour),
      ]}
    />

    <ul className={styles.options}>
      <li className={styles.optionPrimary}>
        <span className={styles.badge}>Recommended</span>
        <h3 className={styles.optionTitle}>Bring the older chunks up to date</h3>
        <p className={styles.optionBody}>
          One run, the cost above, and every passage is found on the same terms
          again. It can be stopped and picked up later, and it skips whatever it
          has already done.
        </p>
        <button
          type="button"
          className={styles.primary}
          onClick={onBackfill}
          disabled={busy}
        >
          {busy ? 'Working through them…' : 'Bring them up to date'}
        </button>
      </li>

      <li className={styles.optionSecondary}>
        <h3 className={styles.optionTitle}>Enrich only what arrives from now on</h3>
        <p className={styles.optionBody}>
          Nothing more to pay today. The {formatNumber(chunksLeftBehind)} chunks
          already indexed go on losing comparisons to newer ones, for a reason
          that is not their relevance, and that does not settle by itself.
        </p>
        <button
          type="button"
          className={styles.secondary}
          onClick={onOnlyNew}
          disabled={busy}
        >
          Leave them as they are
        </button>
      </li>
    </ul>

    {error && <p className={styles.error} role="alert">{error}</p>}

    <div className={styles.footer}>
      <button type="button" className={styles.link} onClick={onLater} disabled={busy}>
        Decide later
      </button>
      <span className={styles.footerAside}>
        The count stays above the document list until this is answered.
      </span>
    </div>

    <p className={styles.footnote}>
      Published figures put the reduction in failed retrievals at about a third.{' '}
      {PUBLISHED_SOURCE} The number for this deployment comes from running the
      retrieval eval on these documents.
    </p>
  </Dialog>
);
