/**
 * Measurement dashboard (admin).
 */

import { useCallback, useEffect, useState } from 'react';
import studioStyles from '../studio/Studio.module.css';
import styles from './Measure.module.css';
import { eventStats, warmupZones, zoneCacheStats } from '../../lib/api';
import {
  formatCount,
  formatCtr,
  formatPValue,
  formatUplift,
  verdict,
  type ArmName,
  type CacheStats,
  type EventStats,
  type WarmupResult,
} from '../../lib/measure';
import { clearSession, getSession, type AdminSession } from '../../lib/session';
import { ConnectGate } from '../studio/ConnectGate';

const TONE_CLASS = {
  success: styles.toneSuccess,
  warning: styles.toneWarning,
  muted: styles.toneMuted,
  neutral: styles.toneNeutral,
} as const;

const ARM_ORDER: ArmName[] = ['personalized', 'control', 'none'];

const ARM_LABEL: Record<ArmName, string> = {
  personalized: 'Personalized',
  control: 'Control (holdout)',
  none: 'No experiment',
};


const ZoneStats = ({ session }: { session: AdminSession }) => {
  const [zoneId, setZoneId] = useState('');
  const [stats, setStats] = useState<EventStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onLoad = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!zoneId.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setStats(await eventStats(session, zoneId.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  const armRows = stats
    ? ARM_ORDER.filter((arm) => stats.arms[arm]).map((arm) => ({
      arm,
      ...stats.arms[arm]!,
    }))
    : [];
  const view = stats ? verdict(stats) : null;

  return (
    <section className={`st-glass ${studioStyles.testerCard}`}>
      <h2 className="st-section-title">Uplift by zone</h2>
      <p className={studioStyles.testerSub}>
        Does personalization beat the holdout? CTR per arm, uplift and the
        two-proportion z-test for one zone.
      </p>

      <form className={studioStyles.testerForm} onSubmit={onLoad}>
        <input
          type="text"
          value={zoneId}
          onChange={(e) => setZoneId(e.target.value)}
          placeholder="zone_id (as used by your GenUIZone, e.g. homepage-hero)"
          aria-label="Zone ID"
          className={studioStyles.testerInput}
        />
        <button type="submit" className={studioStyles.primaryButton} disabled={busy}>
          {busy ? 'Loading…' : 'Load stats →'}
        </button>
      </form>

      {error && <p className={studioStyles.error} role="alert">{error}</p>}

      {stats && view && (
        <>
          <div className={`${styles.verdict} ${TONE_CLASS[view.tone]}`} role="status">
            <p className={styles.verdictLabel}>{view.label}</p>
            <p className={styles.verdictDetail}>{view.detail}</p>
          </div>

          <div className={styles.tiles}>
            <div className={styles.tile}>
              <p className={styles.tileLabel}>Uplift</p>
              <p className={styles.tileValue}>{formatUplift(stats.uplift_percent)}</p>
              <p className={styles.tileNote}>personalized vs control CTR</p>
            </div>
            <div className={styles.tile}>
              <p className={styles.tileLabel}>Personalized CTR</p>
              <p className={styles.tileValue}>{formatCtr(stats.arms.personalized?.ctr)}</p>
            </div>
            <div className={styles.tile}>
              <p className={styles.tileLabel}>Control CTR</p>
              <p className={styles.tileValue}>{formatCtr(stats.arms.control?.ctr)}</p>
            </div>
            {stats.significance && (
              <div className={styles.tile}>
                <p className={styles.tileLabel}>z-test</p>
                <p className={styles.tileValue}>{formatPValue(stats.significance.p_value)}</p>
                <p className={styles.tileNote}>z = {stats.significance.z_score}</p>
              </div>
            )}
          </div>

          {armRows.length > 0 && (
            <table className={studioStyles.table}>
              <thead>
                <tr>
                  <th scope="col">Arm</th>
                  <th scope="col">Impressions</th>
                  <th scope="col">Clicks</th>
                  <th scope="col">CTR</th>
                </tr>
              </thead>
              <tbody>
                {armRows.map((row) => (
                  <tr key={row.arm}>
                    <td>{ARM_LABEL[row.arm]}</td>
                    <td>{formatCount(row.impression)}</td>
                    <td>{formatCount(row.click)}</td>
                    <td>{formatCtr(row.ctr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {stats.holdout_percent != null && (
            <p className={styles.footnote}>
              Holdout is set to {stats.holdout_percent}% of traffic
              (HOLDOUT_PERCENT). Arms fill up automatically as GenUIZone
              emits impressions and clicks.
            </p>
          )}
        </>
      )}
    </section>
  );
};


const WARMUP_PLACEHOLDER = `[
  {
    "zone_id": "homepage-hero",
    "base_prompt": "Curate the hero content for this audience",
    "user_profile": { "role": "developer", "interests": ["ai"] }
  }
]`;

const OpsPanel = ({ session }: { session: AdminSession }) => {
  const [cache, setCache] = useState<CacheStats | null>(null);
  const [cacheError, setCacheError] = useState<string | null>(null);

  const [zonesJson, setZonesJson] = useState(WARMUP_PLACEHOLDER);
  const [warmup, setWarmup] = useState<WarmupResult | null>(null);
  const [warmupError, setWarmupError] = useState<string | null>(null);
  const [warming, setWarming] = useState(false);

  const refreshCache = useCallback(async () => {
    setCacheError(null);
    try {
      setCache(await zoneCacheStats(session));
    } catch (e) {
      setCache(null);
      setCacheError(e instanceof Error ? e.message : 'Request failed');
    }
  }, [session]);

  useEffect(() => {
    void refreshCache();
  }, [refreshCache]);

  const onWarmup = async (event: React.FormEvent) => {
    event.preventDefault();
    setWarmupError(null);
    setWarmup(null);

    let zones: unknown;
    try {
      zones = JSON.parse(zonesJson);
    } catch {
      setWarmupError('Not valid JSON. Expected an array of zone render requests.');
      return;
    }
    if (!Array.isArray(zones) || zones.length === 0) {
      setWarmupError('Expected a non-empty JSON array of zone render requests.');
      return;
    }

    setWarming(true);
    try {
      setWarmup(await warmupZones(session, zones));
      void refreshCache();
    } catch (e) {
      setWarmupError(e instanceof Error ? e.message : 'Warmup failed');
    } finally {
      setWarming(false);
    }
  };

  return (
    <section className={`st-glass ${studioStyles.testerCard}`}>
      <div className={studioStyles.tableHeader}>
        <h2 className="st-section-title">Ops: cache &amp; warmup</h2>
        <button
          type="button"
          className={studioStyles.disconnect}
          onClick={() => void refreshCache()}
        >
          Refresh
        </button>
      </div>

      {cacheError && <p className={studioStyles.error} role="alert">{cacheError}</p>}

      {cache && (
        <div className={styles.tiles}>
          <div className={styles.tile}>
            <p className={styles.tileLabel}>Cache</p>
            <p className={styles.tileValue}>{cache.enabled ? 'On' : 'Off'}</p>
          </div>
          <div className={styles.tile}>
            <p className={styles.tileLabel}>Backend</p>
            <p className={styles.tileValue}>{cache.backend}</p>
            <p className={styles.tileNote}>redis: {cache.redis}</p>
          </div>
          <div className={styles.tile}>
            <p className={styles.tileLabel}>Fresh / stale TTL</p>
            <p className={styles.tileValue}>
              {formatCount(cache.fresh_ttl)}s / {formatCount(cache.stale_ttl)}s
            </p>
          </div>
          <div className={styles.tile}>
            <p className={styles.tileLabel}>In-memory entries</p>
            <p className={styles.tileValue}>{formatCount(cache.memory_entries)}</p>
          </div>
        </div>
      )}

      <form onSubmit={onWarmup}>
        <label className={studioStyles.fieldLabel} htmlFor="ms-warmup" style={{ marginBottom: "1rem", display: "block" }}>
          Segment warmup (one zone render request per archetype)
        </label>
        <textarea
          id="ms-warmup"
          className={styles.jsonArea}
          value={zonesJson}
          onChange={(e) => setZonesJson(e.target.value)}
          spellCheck={false}
        />
        <p className={styles.footnote} style={{ marginBottom: "2rem", marginTop: "1rem" }}>
          Runs the same pipeline as live traffic and fills the same cache
          keys, so real users hit a warm cache. Typically wired to a deploy
          hook or cron; this button is the manual trigger.
        </p>
        <button
          type="submit"
          className={`${studioStyles.primaryButton} ${styles.warmupButton}`}
          disabled={warming}
        >
          {warming ? 'Warming…' : (
            <>
              Warm up
              <span className={styles.warmupArrow} aria-hidden="true">→</span>
            </>
          )}
        </button>
      </form>

      {warmupError && <p className={studioStyles.error} role="alert">{warmupError}</p>}

      {warmup && (
        <div style={{ marginTop: "2rem" }}>
          <p className={studioStyles.testerSub}>
            Warmed {warmup.warmed} / {warmup.results.length}
            {warmup.failed > 0 ? `, ${warmup.failed} failed` : ''}
          </p>
          {warmup.results.map((entry, i) => (
            <div key={`${entry.zone_id}-${i}`} className={styles.warmupRow}>
              <span className={styles.warmupZone}>{entry.zone_id}</span>
              <span className={styles.warmupSegment}>{entry.segment}</span>
              {entry.success ? (
                <span className={studioStyles.uploadDone}>Warmed ✓</span>
              ) : (
                <span className={studioStyles.uploadError}>{entry.error ?? 'Failed'}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
};


export const MeasurePage = () => {
  const [session, setSession] = useState<AdminSession | null>(() => getSession());

  if (!session) {
    return <ConnectGate onConnected={setSession} />;
  }

  return (
    <main className={studioStyles.page} style={{ marginTop: "3rem" }}>
      <div className={studioStyles.pageHeader}>
        <span className={studioStyles.connectedTo}>
          Connected to <code>{session.baseUrl}</code>
        </span>
        <button
          type="button"
          className={studioStyles.disconnect}
          onClick={() => {
            clearSession();
            setSession(null);
          }}
        >
          Disconnect
        </button>
      </div>

      <ZoneStats session={session} />
      <OpsPanel session={session} />
    </main>
  );
};

export default MeasurePage;
