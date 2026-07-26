/**
 * Zone governance.
 */

import { useCallback, useEffect, useState } from 'react';
import studioStyles from '../studio/Studio.module.css';
import measureStyles from '../measure/Measure.module.css';
import previewStyles from '../preview/Preview.module.css';
import styles from './Zones.module.css';
import {
  approveZoneConfig,
  deleteZoneConfig,
  discardZoneDraft,
  getZoneConfig,
  listZoneConfigs,
  saveZoneDraft,
  type ZoneConfigDetail,
  type ZoneGovernedConfig,
  type ZoneListEntry,
} from '../../lib/api';
import type { RenderProfile } from '../../lib/segment';
import { getSession, sessionId, type AdminSession } from '../../lib/session';
import { ConnectGate } from '../studio/ConnectGate';
import { ConsoleHeader } from '../studio/ConsoleHeader';
import { AudienceMatrix } from '../preview/AudienceMatrix';

const EMPTY_CONFIG: ZoneGovernedConfig = {
  base_prompt: 'Show relevant content for this user',
  context_prompt: null,
  pinned_content: [],
  preferred_component_type: null,
  max_items: 6,
  max_components: null,
};

const formatWhen = (iso: string | null): string => {
  if (!iso) return '-';
  const then = Date.parse(iso);
  return Number.isNaN(then) ? '-' : new Date(then).toLocaleString();
};

const StatusPill = ({ entry }: { entry: ZoneListEntry }) => {
  const cls =
    entry.status === 'approved'
      ? `${styles.statusPill} ${styles.statusApproved}`
      : entry.status === 'draft'
        ? `${styles.statusPill} ${styles.statusDraft}`
        : styles.statusPill;
  return (
    <span>
      <span className={cls}>{entry.status}</span>
      {entry.status === 'approved' && entry.has_draft && (
        <span className={styles.draftBadge}>draft pending</span>
      )}
    </span>
  );
};

const ZoneEditor = ({
  session,
  zoneId,
  onChanged,
}: {
  session: AdminSession;
  zoneId: string;
  onChanged: () => void;
}) => {
  const [detail, setDetail] = useState<ZoneConfigDetail | null>(null);
  const [basePrompt, setBasePrompt] = useState(EMPTY_CONFIG.base_prompt);
  const [contextPrompt, setContextPrompt] = useState('');
  const [pinnedJson, setPinnedJson] = useState('[]');
  const [preferredType, setPreferredType] = useState('');
  const [maxItems, setMaxItems] = useState('6');
  const [maxComponents, setMaxComponents] = useState('');
  const [baseVersion, setBaseVersion] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setPreviewOpen(false);
    try {
      const loaded = await getZoneConfig(session, zoneId);
      setDetail(loaded);
      const config = loaded.draft?.config ?? loaded.approved?.config ?? EMPTY_CONFIG;
      setBasePrompt(config.base_prompt);
      setContextPrompt(config.context_prompt ?? '');
      setPinnedJson(JSON.stringify(config.pinned_content, null, 2));
      setPreferredType(config.preferred_component_type ?? '');
      setMaxItems(String(config.max_items));
      setMaxComponents(config.max_components == null ? '' : String(config.max_components));
      setBaseVersion(
        Math.max(loaded.draft?.version ?? 0, loaded.approved?.version ?? 0) || null,
      );
      setNotice(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the zone config');
    }
  }, [session, zoneId]);

  useEffect(() => {
    void load();
  }, [load]);

  const buildConfig = (): Record<string, unknown> => {
    let pinned: unknown = [];
    const raw = pinnedJson.trim();
    if (raw) {
      try {
        pinned = JSON.parse(raw);
      } catch {
        throw new Error('Pinned content is not valid JSON. Expected an array (or leave it empty).');
      }
      if (!Array.isArray(pinned)) {
        throw new Error('Pinned content must be a JSON array of pinned items.');
      }
    }
    const items = Number.parseInt(maxItems, 10);
    if (!Number.isFinite(items) || items < 1) {
      throw new Error('Max items must be a positive number.');
    }
    const components = maxComponents.trim() === '' ? null : Number.parseInt(maxComponents, 10);
    if (components !== null && (!Number.isFinite(components) || components < 1 || components > 10)) {
      throw new Error('Component budget must be between 1 and 10 (or empty for the deployment default).');
    }
    return {
      base_prompt: basePrompt,
      context_prompt: contextPrompt.trim() || null,
      pinned_content: pinned,
      preferred_component_type: preferredType.trim() || null,
      max_items: items,
      max_components: components,
    };
  };

  const saveDraft = async (): Promise<boolean> => {
    setError(null);
    setNotice(null);
    let config: Record<string, unknown>;
    try {
      config = buildConfig();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid config');
      return false;
    }
    setBusy(true);
    try {
      const saved = await saveZoneDraft(session, zoneId, config, baseVersion);
      setDetail((d) => (d ? { ...d, draft: saved.record } : d));
      setBaseVersion(saved.record.version);
      setNotice(
        `Draft v${saved.record.version} saved. Production still serves ` +
        (detail?.approved ? `approved v${detail.approved.version}.` : 'the host page props.') +
        (saved.storage === 'memory'
          ? ' WARNING: Redis is unreachable, this draft lives in one worker\'s memory and is lost on restart.'
          : ''),
      );
      onChanged();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const saveAndPreview = async () => {
    if (await saveDraft()) setPreviewOpen(true);
  };

  const approve = async () => {
    const version = detail?.draft?.version ?? baseVersion;
    if (
      !window.confirm(
        `Approve draft v${version} for zone "${zoneId}"? Every render of this zone starts serving it immediately (host page props are ignored).`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const approved = await approveZoneConfig(session, zoneId, baseVersion);
      setDetail((d) => (d ? { ...d, approved: approved.record, draft: null } : d));
      setBaseVersion(approved.record.version);
      setNotice(`v${approved.record.version} approved: it is now what production serves.`);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approve failed');
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    if (!window.confirm(`Discard the draft for "${zoneId}"? The approved config keeps serving.`)) return;
    setBusy(true);
    setError(null);
    try {
      await discardZoneDraft(session, zoneId);
      await load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Discard failed');
    } finally {
      setBusy(false);
    }
  };

  const removeConfig = async () => {
    if (
      !window.confirm(
        `Delete the whole registry entry for "${zoneId}"? The zone goes back to whatever the host page props say (ungoverned).`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteZoneConfig(session, zoneId);
      await load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  const hasDraft = detail?.draft != null;
  const hasAnything = hasDraft || detail?.approved != null;

  return (
    <>
      <section className={`st-glass ${studioStyles.testerCard}`}>
        <h2 className="st-section-title">Edit “{zoneId}”</h2>
        <div className={styles.versionChips}>
          {detail?.approved && (
            <span className={`${styles.statusPill} ${styles.statusApproved}`}>
              approved v{detail.approved.version} · serving
            </span>
          )}
          {detail?.draft && (
            <span className={`${styles.statusPill} ${styles.statusDraft}`}>
              draft v{detail.draft.version} · not served
            </span>
          )}
          {!hasAnything && (
            <span className={styles.statusPill}>
              ungoverned · host page props drive this zone
            </span>
          )}
        </div>

        <div className={previewStyles.configFields}>
          <div>
            <label className={studioStyles.fieldLabel} htmlFor="zg-base">Base prompt</label>
            <textarea
              id="zg-base"
              className={`${studioStyles.field} ${previewStyles.promptArea}`}
              value={basePrompt}
              onChange={(e) => setBasePrompt(e.target.value)}
            />
          </div>
          <div>
            <label className={studioStyles.fieldLabel} htmlFor="zg-context">Context prompt (optional)</label>
            <textarea
              id="zg-context"
              className={`${studioStyles.field} ${previewStyles.promptArea}`}
              value={contextPrompt}
              onChange={(e) => setContextPrompt(e.target.value)}
            />
          </div>
          <div>
            <label className={studioStyles.fieldLabel} htmlFor="zg-pinned">
              Pinned content (JSON array, always enforced in the render)
            </label>
            <textarea
              id="zg-pinned"
              className={measureStyles.jsonArea}
              value={pinnedJson}
              onChange={(e) => setPinnedJson(e.target.value)}
              spellCheck={false}
            />
          </div>
          <div className={styles.numberFields}>
            <div>
              <label className={studioStyles.fieldLabel} htmlFor="zg-type">Preferred component type</label>
              <input
                id="zg-type"
                type="text"
                className={studioStyles.field}
                placeholder="e.g. bento (empty = model's choice)"
                value={preferredType}
                onChange={(e) => setPreferredType(e.target.value)}
                spellCheck={false}
              />
            </div>
            <div>
              <label className={studioStyles.fieldLabel} htmlFor="zg-items">Max items</label>
              <input
                id="zg-items"
                type="number"
                min={1}
                className={studioStyles.field}
                value={maxItems}
                onChange={(e) => setMaxItems(e.target.value)}
              />
            </div>
            <div>
              <label className={studioStyles.fieldLabel} htmlFor="zg-budget">Component budget</label>
              <input
                id="zg-budget"
                type="number"
                min={1}
                max={10}
                className={studioStyles.field}
                placeholder="deployment default"
                value={maxComponents}
                onChange={(e) => setMaxComponents(e.target.value)}
              />
            </div>
          </div>
        </div>

        <div className={styles.actionsRow}>
          <button
            type="button"
            className={studioStyles.primaryButton}
            disabled={busy}
            onClick={() => void saveDraft()}
          >
            Save draft
          </button>
          <button
            type="button"
            className={studioStyles.primaryButton}
            disabled={busy}
            onClick={() => void saveAndPreview()}
          >
            Save & preview →
          </button>
          <button
            type="button"
            className={previewStyles.removeBtn}
            disabled={busy || !hasDraft}
            onClick={() => void approve()}
          >
            Approve draft
          </button>
          <button
            type="button"
            className={previewStyles.removeBtn}
            disabled={busy || !hasDraft}
            onClick={() => void discard()}
          >
            Discard draft
          </button>
          <button
            type="button"
            className={previewStyles.removeBtn}
            disabled={busy || !hasAnything}
            onClick={() => void removeConfig()}
          >
            Delete config
          </button>
        </div>

        {error && <p className={studioStyles.error} role="alert">{error}</p>}
        {notice && <p className={styles.previewNote}>{notice}</p>}
      </section>

      {previewOpen && (
        <>
          <p className={styles.previewNote}>
            Rendering the saved draft server-side (preview_draft): this is
            what each audience would be served if you approve. Nothing is
            written to the cache real traffic reads.
          </p>
          <AudienceMatrix
            session={session}
            buildPayload={(profile: RenderProfile) => ({
              zone_id: zoneId,
              preview_draft: true,
              ...profile,
            })}
          />
        </>
      )}
    </>
  );
};

const ZonesWorkbench = ({
  session,
  onSession,
}: {
  session: AdminSession;
  onSession: (next: AdminSession | null) => void;
}) => {
  const [zones, setZones] = useState<ZoneListEntry[]>([]);
  const [storage, setStorage] = useState('redis');
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [newZoneId, setNewZoneId] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const listing = await listZoneConfigs(session);
      setZones(listing.zones);
      setStorage(listing.storage);
    } catch (e) {
      setListError(e instanceof Error ? e.message : 'Failed to list zones');
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const governNew = (event: React.FormEvent) => {
    event.preventDefault();
    const id = newZoneId.trim();
    if (!id) return;
    setSelected(id);
    setNewZoneId('');
  };

  return (
    <main className={studioStyles.page} style={{ marginTop: '3rem' }}>
      <ConsoleHeader session={session} onSession={onSession} />

      <section className={`st-glass ${studioStyles.tableCard}`}>
        <div className={studioStyles.tableHeader}>
          <h2 className="st-section-title">Zones</h2>
          <span className={studioStyles.countPill}>
            {zones.length} zone{zones.length === 1 ? '' : 's'}
          </span>
        </div>

        {storage === 'memory' && (
          <p className={previewStyles.warnBanner} role="alert">
            Redis is unreachable: governance data is currently stored in
            one worker's memory and will be LOST on restart. Fix the
            backend's Redis connection before editing or approving.
          </p>
        )}

        {listError && <p className={studioStyles.error} role="alert">{listError}</p>}

        {loading ? (
          <p className={studioStyles.tableEmpty}>Loading…</p>
        ) : zones.length === 0 ? (
          <p className={studioStyles.tableEmpty}>
            No zones yet. Zones appear here as soon as your site renders
            them (every render reports its zone_id), or govern one by id
            below.
          </p>
        ) : (
          <table className={studioStyles.table}>
            <thead>
              <tr>
                <th scope="col">Zone</th>
                <th scope="col">Status</th>
                <th scope="col">Version</th>
                <th scope="col">Updated</th>
                <th scope="col">Seen in traffic</th>
              </tr>
            </thead>
            <tbody>
              {zones.map((zone) => (
                <tr
                  key={zone.zone_id}
                  className={
                    selected === zone.zone_id
                      ? `${styles.zoneRow} ${styles.zoneRowSelected}`
                      : styles.zoneRow
                  }
                  onClick={() => setSelected(zone.zone_id)}
                >
                  <td className={studioStyles.tdName}>{zone.zone_id}</td>
                  <td><StatusPill entry={zone} /></td>
                  <td>{zone.version ?? '-'}</td>
                  <td className={studioStyles.tdMuted}>{formatWhen(zone.updated_at)}</td>
                  <td className={studioStyles.tdMuted}>{zone.observed ? 'yes' : 'not yet'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <form className={styles.newZoneRow} onSubmit={governNew}>
          <input
            type="text"
            className={studioStyles.field}
            placeholder="Govern a zone by id, e.g. hero"
            aria-label="Zone id to govern"
            value={newZoneId}
            onChange={(e) => setNewZoneId(e.target.value)}
            spellCheck={false}
          />
          <button type="submit" className={studioStyles.primaryButton} disabled={!newZoneId.trim()}>
            Open editor →
          </button>
        </form>
      </section>

      {selected && (
        <ZoneEditor
          key={selected}
          session={session}
          zoneId={selected}
          onChanged={() => void refresh()}
        />
      )}
    </main>
  );
};

export const ZonesPage = () => {
  const [session, setSession] = useState<AdminSession | null>(() => getSession());

  if (!session) {
    return <ConnectGate onConnected={setSession} />;
  }

  return (
    <ZonesWorkbench
      key={sessionId(session)}
      session={session}
      onSession={setSession}
    />
  );
};

export default ZonesPage;
