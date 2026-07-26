/**
 * Console chrome, shared by every admin page.
 */

import { useEffect, useState } from 'react';
import styles from './Studio.module.css';
import { ConnectGate } from './ConnectGate';
import {
  clearSession,
  listSessions,
  sessionId,
  sessionLabel,
  setActiveSession,
  type AdminSession,
} from '../../lib/session';

const ADD_TENANT = 'add-tenant';

export const ConsoleHeader = ({
  session,
  onSession,
}: {
  session: AdminSession;
  onSession: (next: AdminSession | null) => void;
}) => {
  const [adding, setAdding] = useState(false);
  const sessions = listSessions();

  useEffect(() => {
    if (!adding) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAdding(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [adding]);

  return (
    <div className={styles.pageHeader}>
      <span className={styles.connectedTo}>
        Connected to <code>{session.baseUrl}</code>
      </span>

      <div className={styles.headerActions}>
        <label className={styles.tenantPicker}>
          tenant
          <select
            className={styles.tenantSelect}
            value={sessionId(session)}
            onChange={(e) => {
              const picked = e.target.value;
              if (picked === ADD_TENANT) setAdding(true);
              else onSession(setActiveSession(picked));
            }}
          >
            {sessions.map((connected) => (
              <option key={sessionId(connected)} value={sessionId(connected)}>
                {sessionLabel(connected, sessions)}
              </option>
            ))}
            <option value={ADD_TENANT}>+ Connect another tenant…</option>
          </select>
        </label>

        <button
          type="button"
          className={styles.disconnect}
          onClick={() => onSession(clearSession())}
        >
          Disconnect
        </button>
      </div>

      {adding && (
        <div
          className={styles.gateOverlay}
          role="dialog"
          aria-modal="true"
          aria-label="Connect another tenant"
          onClick={() => setAdding(false)}
        >
          <div onClick={(e) => e.stopPropagation()}>
            <ConnectGate
              onConnected={(next) => {
                setAdding(false);
                onSession(next);
              }}
              onCancel={() => setAdding(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
};
