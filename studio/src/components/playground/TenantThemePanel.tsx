/**
 * Tenant bar in the Playground sidebar.
 */

import { useEffect, useState } from 'react';
import styles from './Playground.module.css';
import consoleStyles from '../studio/Studio.module.css';
import { ConnectGate } from '../studio/ConnectGate';
import { getTenantTheme, saveTenantTheme, type TenantThemeResponse } from '../../lib/api';
import {
  getSession,
  listSessions,
  sessionId,
  sessionLabel,
  setActiveSession,
  type AdminSession,
} from '../../lib/session';
import { themeFromTokens, themeTokens, type StudioTheme } from '../../lib/theme';

const ADD_TENANT = ' add-tenant';

interface TenantThemePanelProps {
  theme: StudioTheme;
  onLoad: (theme: StudioTheme) => void;
}

const savedLabel = (stored: TenantThemeResponse | null): string => {
  if (stored === null) return 'checking…';
  if (!stored.theme) return 'nothing saved yet';
  const when = stored.updated_at ? new Date(stored.updated_at) : null;
  return when && !Number.isNaN(when.getTime())
    ? `saved ${when.toLocaleString()}`
    : 'saved';
};

const TenantThemePanel = ({ theme, onLoad }: TenantThemePanelProps) => {
  const [session, setSession] = useState<AdminSession | null>(() => getSession());
  const [sessions, setSessions] = useState<AdminSession[]>(() => listSessions());
  const [connecting, setConnecting] = useState(false);
  const [stored, setStored] = useState<TenantThemeResponse | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!session) return;
    let current = true;
    setStored(null);
    setStatus(null);
    setError(false);
    getTenantTheme(session)
      .then((response) => { if (current) setStored(response); })
      .catch((e: unknown) => {
        if (!current) return;
        setStored({ theme: null, updated_at: null });
        setError(true);
        setStatus(e instanceof Error ? e.message : 'Could not read the saved theme.');
      });
    return () => { current = false; };
  }, [session]);

  const connected = (next: AdminSession) => {
    setConnecting(false);
    setSessions(listSessions());
    setSession(next);
  };

  const onPick = (picked: string) => {
    if (picked === ADD_TENANT) {
      setConnecting(true);
      return;
    }
    setSession(setActiveSession(picked));
  };

  const save = async () => {
    if (!session) return;
    setBusy(true);
    setError(false);
    try {
      const written = await saveTenantTheme(session, themeTokens(theme));
      setStored({ theme: written.theme, updated_at: written.updated_at });
      setStatus(
        written.storage === 'memory'
          ? 'Saved, but this backend has no Redis: the write lives in one ' +
          'worker and is lost on restart.'
          : `Saved to ${session.tenant}.`,
      );
    } catch (e) {
      setError(true);
      setStatus(e instanceof Error ? e.message : 'Save failed.');
    } finally {
      setBusy(false);
    }
  };

  const load = () => {
    if (!stored?.theme) return;
    onLoad(themeFromTokens(stored.theme));
    setError(false);
    setStatus(`Loaded the theme saved for ${session?.tenant}.`);
  };

  return (
    <div className={styles.tenantBlock}>
      <div className={styles.tenantHead}>
        <span className={styles.controlLabel}>Tenant theme</span>
        {session ? (
          <select
            className={styles.select}
            value={sessionId(session)}
            onChange={(event) => onPick(event.target.value)}
            aria-label="Tenant this theme is saved to"
          >
            {sessions.map((connectedSession) => (
              <option key={sessionId(connectedSession)} value={sessionId(connectedSession)}>
                {sessionLabel(connectedSession, sessions)}
              </option>
            ))}
            <option value={ADD_TENANT}>+ Connect another tenant…</option>
          </select>
        ) : (
          <button
            type="button"
            className={styles.tenantButton}
            onClick={() => setConnecting(true)}
          >
            Connect a tenant →
          </button>
        )}
      </div>

      {session && (
        <>
          <span className={styles.tenantNote}>{savedLabel(stored)}</span>
          <div className={styles.tenantActions}>
            <button
              type="button"
              className={styles.tenantButton}
              onClick={load}
              disabled={busy || !stored?.theme}
              title={
                stored?.theme
                  ? 'Replace the controls with the theme saved for this tenant'
                  : 'This tenant has no saved theme yet'
              }
            >
              Load saved
            </button>
            <button
              type="button"
              className={styles.tenantButton}
              onClick={() => void save()}
              disabled={busy}
            >
              {busy ? 'Saving…' : 'Save to tenant'}
            </button>
          </div>

          <details className={consoleStyles.gateHelp}>
            <summary>What does saving do?</summary>
            <p>
              The theme becomes config stored for this tenant and served by{' '}
              <code>GET /api/v1/theme</code>. The library still takes the theme
              as a prop: a host applies the saved one by fetching that endpoint
              once at boot and passing the JSON to <code>theme</code>. Saving
              does not reach into a live page.
            </p>
            <p>
              The Segment Preview renders with the theme saved here, so you can
              see what this tenant is actually served. The exports in Save
              remain the build-time route.
            </p>
          </details>
        </>
      )}

      {status && (
        <p
          className={error ? styles.exportError : styles.tenantStatus}
          role={error ? 'alert' : 'status'}
        >
          {status}
        </p>
      )}

      {connecting && (
        <div
          className={consoleStyles.gateOverlay}
          role="dialog"
          aria-modal="true"
          aria-label="Connect a tenant"
          onClick={() => setConnecting(false)}
        >
          <div onClick={(event) => event.stopPropagation()}>
            <ConnectGate onConnected={connected} onCancel={() => setConnecting(false)} />
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantThemePanel;
