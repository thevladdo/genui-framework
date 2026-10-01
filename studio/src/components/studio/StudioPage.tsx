/**
 * Content Studio (admin).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import styles from './Studio.module.css';
import {
  backfillContext,
  backfillInRuns,
  cancelIngest,
  deleteDocument,
  listDocuments,
  readIngest,
  searchDocuments,
  tooLarge,
  uploadDocument,
  uploadLimitLabel,
  type CorpusState,
  type IngestStatus,
  type KnowledgeDocument,
  type SearchResult,
} from '../../lib/api';
import { clearSession, getSession, isActive, sessionId, type AdminSession } from '../../lib/session';
import { ConnectGate } from './ConnectGate';
import { ConsoleHeader } from './ConsoleHeader';
import { BackfillDialog, CorpusDecision, SpendConfirm } from './CorpusModals';

// Upload zone
const ACCEPT = '.pdf,.docx,.html,.htm,.txt,.md,.png,.jpg,.jpeg,.webp,.tiff';

interface UploadState {
  id: string;
  name: string;
  status: 'uploading' | 'done' | 'error';
  message?: string;
}

interface PendingUpload {
  files: File[];
  chunks: number;
  calls: number;
  promptCache: string | null;
}

interface ActiveIngest {
  id: string;
  name: string;
  position: number;
  total: number;
}

const newIngestId = (): string =>
  crypto.randomUUID?.() ??
  `ingest-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

const elapsedLabel = (since: number): string => {
  const seconds = Math.floor((Date.now() - since) / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
};

const IngestProgress = ({
  active,
  status,
  stopping,
  onStop,
}: {
  active: ActiveIngest;
  status: IngestStatus | null;
  stopping: boolean;
  onStop: () => void;
}) => {
  const [, forceTick] = useState(0);
  const started = status?.started_at ? status.started_at * 1000 : null;

  useEffect(() => {
    const timer = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const counting = (status?.total ?? 0) > 0;
  const percent = counting
    ? Math.min(100, Math.round(((status?.done ?? 0) / (status?.total ?? 1)) * 100))
    : null;

  const phase = stopping
    ? 'Stopping after the batch in flight…'
    : status?.phase === 'contextualizing'
      ? 'Writing the context of each chunk, one model call each'
      : status?.phase === 'cancelled'
        ? 'Stopped. Everything written so far is kept'
        : 'Indexing';

  return (
    <div className={styles.progressPanel} role="status" aria-live="polite">
      <div className={styles.progressHead}>
        <span className={styles.progressName}>{active.name}</span>
        {active.total > 1 && (
          <span className={styles.progressCount}>
            file {active.position} of {active.total}
          </span>
        )}
      </div>

      <div
        className={styles.progressTrack}
        role="progressbar"
        aria-valuenow={percent ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Indexing progress"
      >
        <div
          className={percent === null ? styles.progressBarBusy : styles.progressBar}
          style={percent === null ? undefined : { width: `${percent}%` }}
        />
      </div>

      <p className={styles.progressPhase}>
        {phase}
        {counting && (
          <>
            {' · '}
            <strong>{percent}%</strong>{' '}
            ({(status?.done ?? 0).toLocaleString('en-US')} of{' '}
            {(status?.total ?? 0).toLocaleString('en-US')} chunks)
          </>
        )}
        {started && <> · {elapsedLabel(started)} elapsed</>}
      </p>

      <button
        type="button"
        className={styles.stopButton}
        onClick={onStop}
        disabled={stopping}
      >
        {stopping ? 'Stopping…' : 'Stop this upload'}
      </button>
    </div>
  );
};

const UploadZone = ({
  session,
  corpus,
  onUploaded,
  onCrossed,
}: {
  session: AdminSession;
  corpus: CorpusState | null;
  onUploaded: () => void;
  onCrossed: (chunksLeftBehind: number) => void;
}) => {
  const [dragOver, setDragOver] = useState(false);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [confirming, setConfirming] = useState<PendingUpload | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveIngest | null>(null);
  const [progress, setProgress] = useState<IngestStatus | null>(null);
  const [stopping, setStopping] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const sendAll = useCallback(
    async (files: File[]) => {
      let crossedLeftBehind = 0;

      for (const [index, file] of files.entries()) {
        const ingestId = newIngestId();
        setActive({ id: ingestId, name: file.name, position: index + 1, total: files.length });
        setProgress(null);
        setStopping(false);
        setUploads((u) => [...u, { id: ingestId, name: file.name, status: 'uploading' }]);
        try {
          const report = await uploadDocument(session, file, { ingestId });
          if (report.crosses_threshold && (report.chunks_left_behind ?? 0) > 0) {
            crossedLeftBehind = report.chunks_left_behind ?? 0;
          }
          setUploads((u) =>
            u.map((entry) =>
              entry.id === ingestId
                ? {
                  ...entry,
                  status: report.status === 'partial' ? 'error' : 'done',
                  message: report.status === 'partial'
                    ? report.chunks_failed
                      ? `${report.chunks_failed} ${report.chunks_failed === 1 ? 'chunk' : 'chunks'} not indexed, the previous version is still served: upload it again`
                      : `indexed, but the previous version could not be removed and is still served: upload it again`
                    : report.cancelled
                    ? `stopped, ${report.chunks_indexed} chunks kept`
                    : report.budget_exceeded
                      ? `indexed without context: the hourly cap ran out`
                      : undefined,
                }
                : entry,
            ),
          );
          if (report.cancelled) break;
        } catch (e) {
          setUploads((u) =>
            u.map((entry) =>
              entry.id === ingestId
                ? {
                  ...entry,
                  status: 'error',
                  message: e instanceof Error ? e.message : 'Upload failed',
                }
                : entry,
            ),
          );
        }
      }
      setActive(null);
      setProgress(null);
      onUploaded();
      if (crossedLeftBehind > 0) onCrossed(crossedLeftBehind);
    },
    [session, onUploaded, onCrossed],
  );

  useEffect(() => {
    if (!active) return;
    let stopped = false;

    const poll = async () => {
      try {
        const status = await readIngest(session, active.id);
        if (!stopped) setProgress(status);
      } catch {
        // A poll that fails says nothing about the upload: keep waiting
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [session, active]);

  const stopActive = useCallback(async () => {
    if (!active) return;
    setStopping(true);
    try {
      await cancelIngest(session, active.id);
    } catch {
      setStopping(false);
    }
  }, [session, active]);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return;
      const refused = Array.from(files).filter((file) => tooLarge(file.size, corpus));
      if (refused.length && corpus?.max_upload_bytes !== undefined) {
        const limit = uploadLimitLabel(corpus.max_upload_bytes);
        setUploads((u) => [
          ...u,
          ...refused.map((file) => ({
            id: newIngestId(),
            name: file.name,
            status: 'error' as const,
            message: `not sent: the file is over the ${limit} upload limit`,
          })),
        ]);
      }
      const chosen = Array.from(files).filter((file) => !tooLarge(file.size, corpus));
      if (!chosen.length) return;

      const mayCross =
        corpus !== null &&
        corpus.threshold_tokens > 0 &&
        corpus.tokens < corpus.threshold_tokens;

      if (mayCross) {
        setEstimating(true);
        setEstimateError(null);
        try {
          const estimates = await Promise.all(
            chosen.map((file) => uploadDocument(session, file, { dryRun: true })),
          );
          const calls = estimates.reduce((total, e) => total + e.context_calls, 0);
          const chunks = estimates.reduce((total, e) => total + e.chunks_created, 0);

          if (calls > 0) {
            setConfirming({
              files: chosen,
              chunks,
              calls,
              promptCache: estimates[0]?.prompt_cache ?? null,
            });
            return;
          }
        } catch (e) {
          setEstimateError(
            e instanceof Error
              ? `Could not work out what this upload would cost: ${e.message}`
              : 'Could not work out what this upload would cost',
          );
          return;
        } finally {
          setEstimating(false);
        }
      }

      await sendAll(chosen);
    },
    [session, corpus, sendAll],
  );

  if (active) {
    return (
      <section className={`st-glass ${styles.uploadCard}`}>
        <IngestProgress
          active={active}
          status={progress}
          stopping={stopping}
          onStop={() => void stopActive()}
        />
      </section>
    );
  }

  return (
    <section className={`st-glass ${styles.uploadCard}`}>
      <div
        className={dragOver ? styles.dropzoneActive : styles.dropzone}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          void handleFiles(e.dataTransfer.files);
        }}
      >
        <span className={styles.dropIcon} aria-hidden="true">↥</span>
        <p className={styles.dropTitle}>Drop documents here</p>
        <p className={styles.dropFormats}>
          PDF · DOCX · HTML · TXT · MD · Images
          {corpus?.max_upload_bytes !== undefined &&
            ` · up to ${uploadLimitLabel(corpus.max_upload_bytes)}`}{' '}
          <button
            type="button"
            className={styles.browse}
            onClick={() => inputRef.current?.click()}
          >
            or Browse files
          </button>
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => {
            void handleFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {corpus?.contextual_indexing && (
        <p className={styles.uploadNotice}>
          This knowledge base is past the size where context pays: every chunk
          indexed here costs one model call, on your key.
        </p>
      )}

      {estimating && (
        <p className={styles.uploadNotice} role="status">
          Working out what this upload would cost, before spending anything…
        </p>
      )}

      {estimateError && (
        <p className={styles.uploadErrorNotice} role="alert">
          {estimateError} Nothing was uploaded.
        </p>
      )}

      {uploads.length > 0 && (
        <ul className={styles.uploadList}>
          {uploads.map((upload) => (
            <li key={upload.id} className={styles.uploadItem}>
              <span className={styles.uploadName}>{upload.name}</span>
              {upload.status === 'uploading' && <span className={styles.uploadBusy}>Uploading…</span>}
              {upload.status === 'done' && <span className={styles.uploadDone}>Indexed ✓</span>}
              {upload.status === 'error' && (
                <span className={styles.uploadError}>{upload.message}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {confirming && (
        <SpendConfirm
          chunks={confirming.chunks}
          calls={confirming.calls}
          budgetPerHour={corpus?.budget_per_hour ?? null}
          promptCache={confirming.promptCache}
          onConfirm={() => {
            const pending = confirming.files;
            setConfirming(null);
            void sendAll(pending);
          }}
          onCancel={() => setConfirming(null)}
        />
      )}
    </section>
  );
};

// Knowledge base table
const formatWhen = (iso?: string | null): string => {
  if (!iso) return '-';
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '-';
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? '1 month ago' : `${months} months ago`;
};

const CorpusBanner = ({
  corpus,
  onFix,
}: {
  corpus: CorpusState | null;
  onFix: () => void;
}) => {
  if (!corpus || !corpus.contextual_indexing || corpus.chunks_plain === 0) return null;

  return (
    <div className={styles.corpusBanner}>
      <p className={styles.corpusBannerText}>
        <strong>{corpus.chunks_plain.toLocaleString('en-US')}</strong> of{' '}
        {corpus.chunks_total.toLocaleString('en-US')} chunks were indexed before
        this knowledge base reached the size where context pays, and they compete
        without it. Retrieval stays uneven, against the older documents, until
        they are brought up to date.
      </p>
      <button type="button" className={styles.corpusBannerAction} onClick={onFix}>
        Bring them up to date
      </button>
    </div>
  );
};

const DocumentsTable = ({
  documents,
  corpus,
  loading,
  onDelete,
  onFixCorpus,
}: {
  documents: KnowledgeDocument[];
  corpus: CorpusState | null;
  loading: boolean;
  onDelete: (source: string) => void;
  onFixCorpus: () => void;
}) => (
  <section className={`st-glass ${styles.tableCard}`}>
    <div className={styles.tableHeader}>
      <h2 className="st-section-title">Knowledge base</h2>
      <span className={styles.countPill}>
        {documents.length} document{documents.length === 1 ? '' : 's'}
        {corpus && corpus.chunks_total > 0 && (
          <> · {corpus.chunks_contextualized.toLocaleString('en-US')}/
            {corpus.chunks_total.toLocaleString('en-US')} with context</>
        )}
      </span>
    </div>

    <CorpusBanner corpus={corpus} onFix={onFixCorpus} />

    {loading ? (
      <p className={styles.tableEmpty}>Loading…</p>
    ) : documents.length === 0 ? (
      <p className={styles.tableEmpty}>
        Nothing indexed yet: drop a document above to feed the AI its first source.
      </p>
    ) : (
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Document</th>
            <th scope="col">Type</th>
            <th scope="col">Chunks</th>
            <th scope="col">Uploaded</th>
            <th scope="col" className={styles.thActions}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.source_document}>
              <td className={styles.tdName}>{doc.source_document}</td>
              <td>
                <span className={styles.typePill}>
                  {(doc.file_type ?? 'txt').toUpperCase()}
                </span>
              </td>
              <td>{doc.chunks}</td>
              <td className={styles.tdMuted}>{formatWhen(doc.indexed_at)}</td>
              <td className={styles.tdActions}>
                <button
                  type="button"
                  className={styles.deleteButton}
                  aria-label={`Delete ${doc.source_document}`}
                  onClick={() => onDelete(doc.source_document)}
                >
                  🗑
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </section>
);

// Query tester
const QueryTester = ({ session }: { session: AdminSession }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSearch = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResults(await searchDocuments(session, query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`st-glass ${styles.testerCard}`}>
      <h2 className="st-section-title">Test a query</h2>
      <p className={styles.testerSub}>What would the AI retrieve for this question?</p>

      <form className={styles.testerForm} onSubmit={onSearch}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter a question to test retrieval…"
          aria-label="Test query"
          className={styles.testerInput}
        />
        <button type="submit" className={styles.primaryButton} disabled={busy}>
          {busy ? 'Searching…' : 'Search →'}
        </button>
      </form>

      {error && <p className={styles.error} role="alert">{error}</p>}

      {results !== null && results.length === 0 && !error && (
        <p className={styles.tableEmpty}>
          No passages above the similarity threshold: the AI would see nothing for this query.
        </p>
      )}

      {results?.map((result, i) => (
        <article key={i} className={styles.resultCard}>
          <header className={styles.resultHeader}>
            <span className={styles.scorePill}>{result.score.toFixed(2)}</span>
            <span className={styles.resultSource}>{result.source_document ?? 'unknown'}</span>
            {result.contextualized && (
              <span className={styles.contextPill} title="Indexed behind lines placing it in its document. Those lines are never returned, so they are not in the text below.">
                with context
              </span>
            )}
          </header>
          <p className={styles.resultContent}>{result.content}</p>
        </article>
      ))}
    </section>
  );
};

// Page
const StudioWorkbench = ({
  session,
  onSession,
}: {
  session: AdminSession;
  onSession: (next: AdminSession | null) => void;
}) => {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [corpus, setCorpus] = useState<CorpusState | null>(null);
  const [loading, setLoading] = useState(false);
  const [decision, setDecision] = useState<number | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillError, setBackfillError] = useState<string | null>(null);
  const [backfillOpen, setBackfillOpen] = useState(false);
  const [backfillEstimate, setBackfillEstimate] = useState<
    { chunksPlain: number; calls: number; promptCache: string | null } | null
  >(null);
  const [backfillRemaining, setBackfillRemaining] = useState<number | null>(null);
  const [backfillRun, setBackfillRun] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setDocuments([]);
    try {
      const base = await listDocuments(session);
      setDocuments(base.documents);
      setCorpus(base.corpus);
    } catch {
      // A dead session (expired key, backend down) falls back to the gate, or to another connected tenant when there is one.
      // clearSession drops the active session, so an error for a tenant already left must not reach it.
      if (isActive(session)) onSession(clearSession());
    } finally {
      setLoading(false);
    }
  }, [session, onSession]);

  const runBackfill = useCallback(async () => {
    const ingestId = newIngestId();
    setBackfillRun(ingestId);
    setBackfilling(true);
    setBackfillError(null);
    try {
      const report = await backfillInRuns(session, ingestId, setBackfillRemaining);
      const remaining = report.chunks_plain_remaining ?? 0;
      if (remaining === 0 || report.status === 'cancelled') {
        setDecision(null);
        setBackfillOpen(false);
      } else {
        setDecision(remaining);
      }
    } catch (e) {
      setBackfillError(e instanceof Error ? e.message : 'Backfill failed');
    } finally {
      setBackfilling(false);
      setBackfillRemaining(null);
      setBackfillRun(null);
      void refresh();
    }
  }, [session, refresh]);

  const openBackfill = useCallback(async () => {
    setBackfillOpen(true);
    setBackfillEstimate(null);
    setBackfillError(null);
    try {
      const report = await backfillContext(session, { dryRun: true });
      setBackfillEstimate({
        chunksPlain: report.chunks_plain,
        calls: report.chunks_plain,
        promptCache: report.prompt_cache ?? null,
      });
    } catch (e) {
      setBackfillError(
        e instanceof Error
          ? `Could not work out what this costs: ${e.message}`
          : 'Could not work out what this costs',
      );
    }
  }, [session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onDelete = async (source: string) => {
    if (!window.confirm(`Delete "${source}" and all its chunks from tenant "${session.tenant}"?`)) return;
    setDeleteError(null);
    try {
      await deleteDocument(session, source);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      void refresh();
    }
  };

  return (
    <main className={styles.page} style={{ marginTop: "3rem" }}>
      <ConsoleHeader session={session} onSession={onSession} />

      <UploadZone
        session={session}
        corpus={corpus}
        onUploaded={() => void refresh()}
        onCrossed={setDecision}
      />
      {deleteError && <p className={styles.error} role="alert">{deleteError}</p>}
      <DocumentsTable
        documents={documents}
        corpus={corpus}
        loading={loading}
        onDelete={onDelete}
        onFixCorpus={() => void openBackfill()}
      />
      <QueryTester session={session} />

      {backfillOpen && (
        <BackfillDialog
          estimate={backfillEstimate}
          budgetPerHour={corpus?.budget_per_hour ?? null}
          running={backfilling}
          remaining={backfillRemaining}
          error={backfillError}
          onStart={() => void runBackfill()}
          onStop={backfillRun ? () => void cancelIngest(session, backfillRun) : undefined}
          onClose={() => setBackfillOpen(false)}
        />
      )}

      {decision !== null && (
        <CorpusDecision
          chunksLeftBehind={decision}
          calls={decision}
          budgetPerHour={corpus?.budget_per_hour ?? null}
          busy={backfilling}
          error={backfillError}
          onBackfill={() => void runBackfill()}
          onOnlyNew={() => setDecision(null)}
          onLater={() => setDecision(null)}
        />
      )}
    </main>
  );
};

export const StudioPage = () => {
  const [session, setSession] = useState<AdminSession | null>(() => getSession());

  if (!session) {
    return <ConnectGate onConnected={setSession} />;
  }

  return (
    <StudioWorkbench
      key={sessionId(session)}
      session={session}
      onSession={setSession}
    />
  );
};

export default StudioPage;
