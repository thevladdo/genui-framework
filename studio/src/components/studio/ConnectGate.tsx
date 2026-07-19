/**
 * Admin connect gate, shared by the Content Studio and the Measurement dashboard: one sessionStorage session unlocks both tools.
 */

import { useState } from 'react';
import styles from './Studio.module.css';
import { verifySession } from '../../lib/api';
import { normalizeBaseUrl, saveSession, type AdminSession } from '../../lib/session';

export const ConnectGate = ({ onConnected }: { onConnected: (s: AdminSession) => void }) => {
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
