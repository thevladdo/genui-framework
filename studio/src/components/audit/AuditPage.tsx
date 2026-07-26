/**
 * Audit viewer.
 */

import { useCallback, useEffect, useState } from 'react';
import studioStyles from '../studio/Studio.module.css';
import previewStyles from '../preview/Preview.module.css';
import zoneStyles from '../zones/Zones.module.css';
import styles from './Audit.module.css';
import {
  queryAudit,
  type AuditEntry,
  type AuditQueryResponse,
} from '../../lib/api';
import { getSession, sessionId, type AdminSession } from '../../lib/session';
import { ConnectGate } from '../studio/ConnectGate';
import { ConsoleHeader } from '../studio/ConsoleHeader';

const PAGE_SIZE = 50;
const KNOWN_EVENTS = [
  'zone_render',
  'query',
  'profile_sync',
  'profile_delete',
  'document_upload',
  'document_delete',
  'zone_config_change',
  'content_policy_change',
  'theme_change',
];

const asText = (value: unknown): string =>
  typeof value === 'string' ? value : JSON.stringify(value);

const SearchIcon = () => (
  <svg
    className={styles.searchIcon}
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    aria-hidden="true"
  >
    <circle cx="7" cy="7" r="4.5" />
    <path d="m11 11 3.5 3.5" />
  </svg>
);

const EntryDetail = ({ entry }: { entry: AuditEntry }) => {
  const sanitization = entry.sanitization;
  const sanitizationRows = sanitization
    ? [
      { label: 'Removed links', items: sanitization.removed_urls ?? [] },
      {
        label: 'Dropped components',
        items: (sanitization.dropped_components ?? []).map(asText),
      },
      {
        label: 'Removed numbers',
        items: (sanitization.removed_numbers ?? []).map(asText),
      },
      {
        label: 'Policy violations',
        items: (sanitization.policy_violations ?? []).map(asText),
      },
    ].filter((row) => row.items.length > 0)
    : [];
  const removedCount = sanitizationRows.reduce(
    (sum, row) => sum + row.items.length,
    0,
  );

  const metaRows: Array<{ label: string; value: string }> = [
    { label: 'Event', value: entry.event ?? '-' },
    { label: 'User', value: entry.user_id ?? 'anonymous' },
    { label: 'Zone', value: entry.zone_id ?? '-' },
    { label: 'Page', value: entry.page ?? '-' },
    { label: 'Segment', value: entry.cache?.segment ?? '-' },
    {
      label: 'Cache',
      value: entry.cache
        ? `${entry.cache.status ?? '-'} (${entry.cache.strategy ?? '-'})` +
        (entry.cache.age_seconds != null
          ? `, age ${entry.cache.age_seconds}s`
          : '')
        : '-',
    },
    { label: 'Render id', value: entry.render_id ?? '-' },
    { label: 'Arm', value: entry.arm ?? '-' },
    {
      label: 'Personalized',
      value:
        entry.personalization_applied == null
          ? '-'
          : String(entry.personalization_applied),
    },
    { label: 'Admin key', value: entry.key ?? '-' },
  ];

  return (
    <section className={`st-glass ${studioStyles.testerCard}`}>
      <h2 className="st-section-title">
        Event detail <span className={studioStyles.tdMuted}>{entry.ts}</span>
      </h2>

      <div className={previewStyles.metaList}>
        {metaRows.map((row) => (
          <div className={previewStyles.metaRow} key={row.label}>
            <span className={previewStyles.metaLabel}>{row.label}</span>
            <span className={previewStyles.metaValue}>{row.value}</span>
          </div>
        ))}

        {(entry.component_types?.length ?? 0) > 0 && (
          <div className={previewStyles.metaRow}>
            <span className={previewStyles.metaLabel}>Shown</span>
            <span className={previewStyles.metaValue}>
              {entry.component_types?.join(', ')}
            </span>
          </div>
        )}
        {(entry.shown_titles?.length ?? 0) > 0 && (
          <div className={previewStyles.metaRow}>
            <span className={previewStyles.metaLabel}>Titles</span>
            <span className={previewStyles.metaValue}>
              {entry.shown_titles?.join(' · ')}
            </span>
          </div>
        )}
        {(entry.shown_links?.length ?? 0) > 0 && (
          <div className={previewStyles.metaRow}>
            <span className={previewStyles.metaLabel}>Links</span>
            <ul className={previewStyles.sanitList}>
              {entry.shown_links?.map((link) => <li key={link}>{link}</li>)}
            </ul>
          </div>
        )}

        <div className={previewStyles.metaRow}>
          <span className={previewStyles.metaLabel}>Guarantees</span>
          {sanitization == null ? (
            <span className={previewStyles.metaValue}>
              not recorded for this event
            </span>
          ) : removedCount === 0 ? (
            <span
              className={`${previewStyles.metaValue} ${previewStyles.sanitClean}`}
            >
              nothing removed by the guarantee chain
            </span>
          ) : (
            <span className={previewStyles.metaValue}>
              {removedCount} item{removedCount === 1 ? '' : 's'} removed before
              serving
            </span>
          )}
        </div>
        {sanitizationRows.map((row) => (
          <div className={previewStyles.metaRow} key={row.label}>
            <span className={previewStyles.metaLabel}>{row.label}</span>
            <ul className={previewStyles.sanitList}>
              {row.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <details className={styles.rawToggle}>
        <summary>Raw audit line</summary>
        <pre className={styles.rawJson}>{JSON.stringify(entry, null, 2)}</pre>
      </details>
    </section>
  );
};

const AuditWorkbench = ({
  session,
  onSession,
}: {
  session: AdminSession;
  onSession: (next: AdminSession | null) => void;
}) => {
  const [userId, setUserId] = useState('');
  const [zoneId, setZoneId] = useState('');
  const [event, setEvent] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<AuditQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  const load = useCallback(
    async (nextOffset: number) => {
      setLoading(true);
      setError(null);
      setSelected(null);
      try {
        const result = await queryAudit(session, {
          user_id: userId.trim() || undefined,
          zone_id: zoneId.trim() || undefined,
          event: event.trim() || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          limit: PAGE_SIZE,
          offset: nextOffset,
        });
        setData(result);
        setOffset(nextOffset);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Audit query failed');
      } finally {
        setLoading(false);
      }
    },
    [session, userId, zoneId, event, dateFrom, dateTo],
  );

  useEffect(() => {
    void load(0);
  }, [session]);

  const search = (e: React.FormEvent) => {
    e.preventDefault();
    void load(0);
  };

  const entries = data?.entries ?? [];

  return (
    <main className={studioStyles.page} style={{ marginTop: '3rem' }}>
      <ConsoleHeader session={session} onSession={onSession} />

      <section className={`st-glass ${studioStyles.tableCard}`}>
        <div className={studioStyles.tableHeader}>
          <h2 className="st-section-title">Audit trail</h2>
          <span className={studioStyles.countPill}>
            {entries.length}
            {data?.has_more ? '+' : ''} event{entries.length === 1 ? '' : 's'}
          </span>
        </div>

        <form onSubmit={search}>
          <div className={styles.filtersGrid}>
            <div className={styles.fieldGroup}>
              <label htmlFor="au-user">User id</label>
              <input
                id="au-user"
                type="text"
                className={studioStyles.field}
                placeholder="any user"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                spellCheck={false}
              />
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="au-zone">Zone id</label>
              <input
                id="au-zone"
                type="text"
                className={studioStyles.field}
                placeholder="any zone"
                value={zoneId}
                onChange={(e) => setZoneId(e.target.value)}
                spellCheck={false}
              />
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="au-event">Event</label>
              <select
                id="au-event"
                className={studioStyles.field}
                value={event}
                onChange={(e) => setEvent(e.target.value)}
              >
                <option value="">any event</option>
                {KNOWN_EVENTS.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="au-from">From</label>
              <input
                id="au-from"
                type="date"
                className={studioStyles.field}
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className={styles.fieldGroup}>
              <label htmlFor="au-to">To</label>
              <input
                id="au-to"
                type="date"
                className={studioStyles.field}
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
          </div>
          <div className={styles.filtersActions}>
            <button
              type="submit"
              className={`${studioStyles.primaryButton} ${styles.searchBtn}`}
              disabled={loading}
            >
              <SearchIcon />
              Search
            </button>
          </div>
        </form>

        {error && (
          <p className={studioStyles.error} role="alert">
            {error}
          </p>
        )}

        {data && !data.queryable && (
          <p className={previewStyles.warnBanner} role="alert">
            The audit trail is not queryable from this backend: {data.note}
          </p>
        )}

        {loading ? (
          <p className={studioStyles.tableEmpty}>Loading…</p>
        ) : data?.queryable && entries.length === 0 ? (
          <p className={studioStyles.tableEmpty}>
            No audit events match these filters. Events appear here as soon
            as the backend serves renders, queries or profile changes.
          </p>
        ) : entries.length > 0 ? (
          <>
            <table className={studioStyles.table}>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Event</th>
                  <th scope="col">User</th>
                  <th scope="col">Zone</th>
                  <th scope="col">Cache</th>
                  <th scope="col">Segment</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, index) => (
                  <tr
                    key={`${entry.ts}-${index}`}
                    className={
                      selected === index
                        ? `${zoneStyles.zoneRow} ${zoneStyles.zoneRowSelected}`
                        : zoneStyles.zoneRow
                    }
                    onClick={() =>
                      setSelected(selected === index ? null : index)
                    }
                  >
                    <td className={studioStyles.tdMuted}>{entry.ts ?? '-'}</td>
                    <td className={studioStyles.tdName}>{entry.event ?? '-'}</td>
                    <td>{entry.user_id ?? 'anonymous'}</td>
                    <td>{entry.zone_id ?? '-'}</td>
                    <td className={studioStyles.tdMuted}>
                      {entry.cache?.status ?? '-'}
                    </td>
                    <td className={studioStyles.tdMuted}>
                      {entry.cache?.segment ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className={styles.pagerRow}>
              <button
                type="button"
                className={styles.pagerBtn}
                disabled={loading || offset === 0}
                onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}
              >
                ← Newer
              </button>
              <button
                type="button"
                className={styles.pagerBtn}
                disabled={loading || !data?.has_more}
                onClick={() => void load(offset + PAGE_SIZE)}
              >
                Older →
              </button>
              <span className={styles.pagerInfo}>
                {offset + 1}-{offset + entries.length}, newest first
              </span>
            </div>
          </>
        ) : null}
      </section>

      {selected != null && entries[selected] && (
        <EntryDetail entry={entries[selected]} />
      )}
    </main>
  );
};

export const AuditPage = () => {
  const [session, setSession] = useState<AdminSession | null>(() =>
    getSession(),
  );

  if (!session) {
    return <ConnectGate onConnected={setSession} />;
  }

  return (
    <AuditWorkbench
      key={sessionId(session)}
      session={session}
      onSession={setSession}
    />
  );
};

export default AuditPage;
