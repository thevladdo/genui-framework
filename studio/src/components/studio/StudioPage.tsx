/**
 * Content Studio (admin).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import styles from './Studio.module.css';
import {
  deleteDocument,
  listDocuments,
  searchDocuments,
  uploadDocument,
  verifySession,
  type KnowledgeDocument,
  type SearchResult,
} from '../../lib/api';
import {
  clearSession,
  getSession,
  normalizeBaseUrl,
  saveSession,
  type AdminSession,
} from '../../lib/session';

// Connect gate
const ConnectGate = ({ onConnected }: { onConnected: (s: AdminSession) => void }) => {
  const [baseUrl, setBaseUrl] = useState('');
  const [adminKey, setAdminKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    const normalized = normalizeBaseUrl(baseUrl);
    if (!normalized) {
      setError('Enter a valid backend URL (http:// or https://).');
      return;
    }
    if (!adminKey.trim()) {
      setError('Enter your admin key.');
      return;
    }

    const candidate: AdminSession = { baseUrl: normalized, adminKey: adminKey.trim() };
    setBusy(true);
    try {
      await verifySession(candidate);
      saveSession(candidate);
      onConnected(candidate);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.gateWrap}>
      <form className={`st-glass ${styles.gate}`} onSubmit={onSubmit}>
        <div className={styles.gateShield} aria-hidden="true">🛡</div>
        <h1 className={styles.gateTitle}>Connect to your GenUI backend</h1>
        <p className={styles.gateSub}>Enter the URL and admin key for your instance.</p>

        <label className={styles.fieldLabel} htmlFor="st-url">Backend URL</label>
        <input
          id="st-url"
          type="url"
          placeholder="https://your-genui-instance.com"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          className={styles.field}
          autoComplete="off"
          spellCheck={false}
        />

        <label className={styles.fieldLabel} htmlFor="st-key">Admin key</label>
        <input
          id="st-key"
          type="password"
          placeholder="sk_live_…"
          value={adminKey}
          onChange={(e) => setAdminKey(e.target.value)}
          className={styles.field}
          autoComplete="off"
        />

        <p className={styles.gateWarning} role="note">
          ⚠ Never share this key. It grants full read/write access to your knowledge base.
        </p>

        {error && <p className={styles.error} role="alert">{error}</p>}

        <button type="submit" className={styles.primaryButton} disabled={busy}>
          {busy ? 'Connecting…' : 'Connect →'}
        </button>
      </form>

      <p className={styles.gateFootnote}>
        Credentials are stored only in your browser session. Never sent to third parties.
      </p>
    </div>
  );
};

// Upload zone
const ACCEPT = '.pdf,.docx,.html,.htm,.txt,.md,.png,.jpg,.jpeg,.webp,.tiff';

interface UploadState {
  name: string;
  status: 'uploading' | 'done' | 'error';
  message?: string;
}

const UploadZone = ({
  session,
  onUploaded,
}: {
  session: AdminSession;
  onUploaded: () => void;
}) => {
  const [dragOver, setDragOver] = useState(false);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return;

      for (const file of Array.from(files)) {
        setUploads((u) => [...u, { name: file.name, status: 'uploading' }]);
        try {
          await uploadDocument(session, file);
          setUploads((u) =>
            u.map((entry) =>
              entry.name === file.name ? { ...entry, status: 'done' } : entry,
            ),
          );
        } catch (e) {
          // The backend's 422/501 messages are precise (unsupported type,
          // missing extractor backend for images, ...): relay them as-is
          setUploads((u) =>
            u.map((entry) =>
              entry.name === file.name
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
      onUploaded();
    },
    [session, onUploaded],
  );

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
          PDF · DOCX · HTML · TXT · MD · Images{' '}
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

      {uploads.length > 0 && (
        <ul className={styles.uploadList}>
          {uploads.map((upload, i) => (
            <li key={`${upload.name}-${i}`} className={styles.uploadItem}>
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

const DocumentsTable = ({
  documents,
  loading,
  onDelete,
}: {
  documents: KnowledgeDocument[];
  loading: boolean;
  onDelete: (source: string) => void;
}) => (
  <section className={`st-glass ${styles.tableCard}`}>
    <div className={styles.tableHeader}>
      <h2 className="st-section-title">Knowledge base</h2>
      <span className={styles.countPill}>
        {documents.length} document{documents.length === 1 ? '' : 's'}
      </span>
    </div>

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
          </header>
          <p className={styles.resultContent}>{result.content}</p>
        </article>
      ))}
    </section>
  );
};

// Page
export const StudioPage = () => {
  const [session, setSession] = useState<AdminSession | null>(() => getSession());
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    try {
      setDocuments(await listDocuments(session));
    } catch {
      // A dead session (expired key, backend down) falls back to the gate
      clearSession();
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onDelete = async (source: string) => {
    if (!session) return;
    if (!window.confirm(`Delete "${source}" and all its chunks?`)) return;
    try {
      await deleteDocument(session, source);
    } finally {
      void refresh();
    }
  };

  if (!session) {
    return <ConnectGate onConnected={setSession} />;
  }

  return (
    <main className={styles.page}>
      <div className={styles.pageHeader}>
        <span className={styles.connectedTo}>
          Connected to <code>{session.baseUrl}</code>
        </span>
        <button
          type="button"
          className={styles.disconnect}
          onClick={() => {
            clearSession();
            setSession(null);
          }}
        >
          Disconnect
        </button>
      </div>

      <UploadZone session={session} onUploaded={() => void refresh()} />
      <DocumentsTable documents={documents} loading={loading} onDelete={onDelete} />
      <QueryTester session={session} />
    </main>
  );
};

export default StudioPage;
