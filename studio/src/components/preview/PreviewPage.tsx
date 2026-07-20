/**
 * Segment preview (admin): compose audiences, render one zone config
 * live against /zone/render, and compare what each segment is served.
 */

import { useEffect, useState } from 'react';
import {
  ComponentRenderer,
  GenUISection,
  type GenUIComponent,
} from 'genui-framework';
import studioStyles from '../studio/Studio.module.css';
import measureStyles from '../measure/Measure.module.css';
import styles from './Preview.module.css';
import { backendHealth, renderZone } from '../../lib/api';
import {
  buildRenderProfile,
  isFallbackRender,
  sanitizationCount,
  segmentKey,
  toSanitizationReport,
  type Engagement,
  type PreviewRenderResponse,
  type SegmentInput,
} from '../../lib/segment';
import { clearSession, getSession, type AdminSession } from '../../lib/session';
import { ConnectGate } from '../studio/ConnectGate';

// Browsing styles the BehaveAgent classifies into (behave_agent.py)
const USER_TYPES = ['explorer', 'focused', 'scanner', 'deep_reader', 'casual'] as const;
const ENGAGEMENTS: Engagement[] = ['low', 'mid', 'high'];
const MAX_SEGMENTS = 4;

interface SegmentDraft {
  id: number;
  role: string;
  interests: string;
  userType: string;
  engagement: Engagement | '';
}

const PRESETS: Array<Omit<SegmentDraft, 'id'>> = [
  { role: 'developer', interests: 'ai, devtools', userType: 'deep_reader', engagement: 'high' },
  { role: 'marketing manager', interests: 'analytics', userType: 'scanner', engagement: 'low' },
  { role: '', interests: '', userType: '', engagement: '' },
];

const toInput = (draft: SegmentDraft): SegmentInput => ({
  role: draft.role,
  interests: draft.interests.split(',').map((i) => i.trim()).filter(Boolean),
  userType: draft.userType,
  engagement: draft.engagement,
});

const PINNED_PLACEHOLDER = `[
  { "type": "link", "url": "https://example.com/pricing", "title": "See pricing" }
]`;

type ColumnResult = { response: PreviewRenderResponse } | { error: string };

const ColumnRender = ({ response }: { response: PreviewRenderResponse }) => {
  const report = toSanitizationReport(response.meta);
  const removed = sanitizationCount(report);
  const fallback = isFallbackRender(response.meta);
  const cache = response.meta?.cache;

  const sanitizationRows: Array<{ label: string; items: string[] }> = [
    { label: 'URLs removed', items: report.removedUrls },
    { label: 'Components dropped', items: report.droppedComponents },
    { label: 'Numbers ungrounded', items: report.removedNumbers },
    { label: 'Policy violations', items: report.policyViolations },
  ].filter((row) => row.items.length > 0);

  return (
    <>
      {fallback && (
        <p className={styles.warnBanner} role="alert">
          Pinned-only fallback: the backend could not run a generation
          (LLM engine missing or failing). This is NOT what GenUI
          produces when configured. Check LLM_PROVIDER and the engine
          key on the backend, then render again.
        </p>
      )}

      <div className={styles.canvas}>
        {response.components.length > 0 ? (
          <GenUISection>
            <ComponentRenderer
              components={response.components as unknown as GenUIComponent[]}
            />
          </GenUISection>
        ) : (
          <p className={styles.emptyNote}>
            No components came back for this audience (nothing generated,
            or everything was removed by the guarantee chain below).
          </p>
        )}
      </div>

      <div className={styles.metaList}>
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>Cache</span>
          <span className={styles.metaValue}>
            {cache?.status ?? 'unknown'} · strategy {cache?.strategy ?? 'unknown'}
            {cache?.status === 'bypass' && ', live generation, not written to the segment cache'}
          </span>
        </div>
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>Personalized</span>
          <span className={styles.metaValue}>
            {response.personalization_applied ? 'yes' : 'no'}
          </span>
        </div>
        {typeof response.meta?.confidence === 'number' && (
          <div className={styles.metaRow}>
            <span className={styles.metaLabel}>Confidence</span>
            <span className={styles.metaValue}>{response.meta.confidence}</span>
          </div>
        )}
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>Guarantees</span>
          {removed === 0 ? (
            <span className={`${styles.metaValue} ${styles.sanitClean}`}>
              nothing removed by the guarantee chain
            </span>
          ) : (
            <span className={styles.metaValue}>
              {removed} item{removed === 1 ? '' : 's'} removed before serving
            </span>
          )}
        </div>
        {sanitizationRows.map((row) => (
          <div className={styles.metaRow} key={row.label}>
            <span className={styles.metaLabel}>{row.label}</span>
            <ul className={styles.sanitList}>
              {row.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
};

const PreviewWorkbench = ({
  session,
  onDisconnect,
}: {
  session: AdminSession;
  onDisconnect: () => void;
}) => {
  const [zoneId, setZoneId] = useState('studio-preview');
  const [basePrompt, setBasePrompt] = useState(
    'Curate this zone for the audience: pick the components and copy that will resonate most.',
  );
  const [contextPrompt, setContextPrompt] = useState('Homepage, above the fold.');
  const [pinnedJson, setPinnedJson] = useState(PINNED_PLACEHOLDER);

  const [drafts, setDrafts] = useState<SegmentDraft[]>(
    PRESETS.map((preset, i) => ({ id: i, ...preset })),
  );
  const [nextId, setNextId] = useState(PRESETS.length);
  const [results, setResults] = useState<Record<number, ColumnResult>>({});
  const [busy, setBusy] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    backendHealth(session)
      .then((health) => {
        if (!cancelled && health.llm) setLlmConfigured(health.llm === 'configured');
      })
      .catch(() => {
        // Advisory only: a failing render will surface the real error.
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  const patchDraft = (id: number, patch: Partial<SegmentDraft>) =>
    setDrafts((current) =>
      current.map((d) => (d.id === id ? { ...d, ...patch } : d)),
    );

  const addDraft = () => {
    setDrafts((current) => [
      ...current,
      { id: nextId, role: '', interests: '', userType: '', engagement: '' },
    ]);
    setNextId((n) => n + 1);
  };

  const removeDraft = (id: number) => {
    setDrafts((current) => current.filter((d) => d.id !== id));
    setResults(({ [id]: _dropped, ...rest }) => rest);
  };

  const onRender = async (event: React.FormEvent) => {
    event.preventDefault();
    setConfigError(null);

    if (!zoneId.trim()) {
      setConfigError('Enter a zone_id.');
      return;
    }

    let pinned: unknown = [];
    const rawPinned = pinnedJson.trim();
    if (rawPinned) {
      try {
        pinned = JSON.parse(rawPinned);
      } catch {
        setConfigError('Pinned content is not valid JSON. Expected an array (or leave it empty).');
        return;
      }
      if (!Array.isArray(pinned)) {
        setConfigError('Pinned content must be a JSON array of pinned items.');
        return;
      }
    }

    setBusy(true);
    const entries = await Promise.all(
      drafts.map(async (draft): Promise<[number, ColumnResult]> => {
        try {
          const { user_profile, behavior_data } = buildRenderProfile(toInput(draft));
          const response = await renderZone(session, {
            zone_id: zoneId.trim(),
            base_prompt: basePrompt,
            context_prompt: contextPrompt || null,
            pinned_content: pinned,
            // Forces an observable generation (admin only) and never
            // touches the cache real traffic is served from.
            cache_strategy: 'live',
            user_profile,
            behavior_data,
          });
          return [draft.id, { response }];
        } catch (e) {
          return [draft.id, { error: e instanceof Error ? e.message : 'Render failed' }];
        }
      }),
    );
    setResults(Object.fromEntries(entries));
    setBusy(false);
  };

  return (
    <main className={studioStyles.page} style={{ marginTop: '3rem' }}>
      <div className={studioStyles.pageHeader}>
        <span className={studioStyles.connectedTo}>
          Connected to <code>{session.baseUrl}</code>
        </span>
        <button type="button" className={studioStyles.disconnect} onClick={onDisconnect}>
          Disconnect
        </button>
      </div>

      <section className={`st-glass ${studioStyles.testerCard}`}>
        <h2 className="st-section-title">Zone config</h2>
        <p className={studioStyles.testerSub}>
          The prompt and pinned content a page would ship for this zone.
          Every audience below is rendered live against this exact config.
        </p>

        <form onSubmit={onRender}>
          <div className={styles.configFields}>
            <div>
              <label className={studioStyles.fieldLabel} htmlFor="pv-zone">zone_id</label>
              <input
                id="pv-zone"
                type="text"
                className={studioStyles.field}
                value={zoneId}
                onChange={(e) => setZoneId(e.target.value)}
                spellCheck={false}
              />
            </div>
            <div>
              <label className={studioStyles.fieldLabel} htmlFor="pv-base">Base prompt</label>
              <textarea
                id="pv-base"
                className={`${studioStyles.field} ${styles.promptArea}`}
                value={basePrompt}
                onChange={(e) => setBasePrompt(e.target.value)}
              />
            </div>
            <div>
              <label className={studioStyles.fieldLabel} htmlFor="pv-context">Context prompt (optional)</label>
              <textarea
                id="pv-context"
                className={`${studioStyles.field} ${styles.promptArea}`}
                value={contextPrompt}
                onChange={(e) => setContextPrompt(e.target.value)}
              />
            </div>
            <div>
              <label className={studioStyles.fieldLabel} htmlFor="pv-pinned">
                Pinned content (JSON array, always enforced in the render)
              </label>
              <textarea
                id="pv-pinned"
                className={measureStyles.jsonArea}
                value={pinnedJson}
                onChange={(e) => setPinnedJson(e.target.value)}
                spellCheck={false}
              />
            </div>
          </div>

          <div className={styles.renderRow}>
            <button type="submit" className={studioStyles.primaryButton} disabled={busy}>
              {busy ? 'Rendering…' : `Render ${drafts.length} audience${drafts.length === 1 ? '' : 's'} →`}
            </button>
            {drafts.length < MAX_SEGMENTS && (
              <button type="button" className={styles.removeBtn} onClick={addDraft}>
                + Add audience
              </button>
            )}
          </div>
        </form>

        {configError && <p className={studioStyles.error} role="alert">{configError}</p>}

        {llmConfigured === false && (
          <p className={styles.warnBanner} role="alert">
            This backend reports no configured LLM engine (/health: llm
            unconfigured). Renders will degrade to the pinned-only
            fallback until LLM_PROVIDER and its key or base URL are set.
          </p>
        )}
      </section>

      <div className={styles.rows}>
        {drafts.map((draft) => {
          const key = segmentKey(toInput(draft));
          const result = results[draft.id];
          return (
            <section className={`st-glass ${styles.row}`} key={draft.id}>
              <header className={styles.colHead}>
                <span className={styles.keyChip} title="Segment key this audience falls into, computed like the backend segmenter">
                  {key === 'anon' ? 'anon (no signals)' : key}
                </span>
                {drafts.length > 1 && (
                  <button
                    type="button"
                    className={styles.removeBtn}
                    onClick={() => removeDraft(draft.id)}
                  >
                    Remove
                  </button>
                )}
              </header>

              <div className={styles.segFields}>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-role-${draft.id}`}>Role</label>
                  <input
                    id={`pv-role-${draft.id}`}
                    type="text"
                    className={studioStyles.field}
                    placeholder="e.g. developer"
                    value={draft.role}
                    onChange={(e) => patchDraft(draft.id, { role: e.target.value })}
                  />
                </div>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-int-${draft.id}`}>Interests (comma separated)</label>
                  <input
                    id={`pv-int-${draft.id}`}
                    type="text"
                    className={studioStyles.field}
                    placeholder="e.g. ai, sustainability"
                    value={draft.interests}
                    onChange={(e) => patchDraft(draft.id, { interests: e.target.value })}
                  />
                </div>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-type-${draft.id}`}>Browsing style</label>
                  <select
                    id={`pv-type-${draft.id}`}
                    className={studioStyles.field}
                    value={draft.userType}
                    onChange={(e) => patchDraft(draft.id, { userType: e.target.value })}
                  >
                    <option value="">Not set</option>
                    {USER_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-eng-${draft.id}`}>Engagement</label>
                  <select
                    id={`pv-eng-${draft.id}`}
                    className={studioStyles.field}
                    value={draft.engagement}
                    onChange={(e) =>
                      patchDraft(draft.id, { engagement: e.target.value as Engagement | '' })
                    }
                  >
                    <option value="">Not set</option>
                    {ENGAGEMENTS.map((eng) => (
                      <option key={eng} value={eng}>{eng}</option>
                    ))}
                  </select>
                </div>
              </div>

              {result && 'error' in result && (
                <p className={studioStyles.error} role="alert">{result.error}</p>
              )}
              {result && 'response' in result && <ColumnRender response={result.response} />}
            </section>
          );
        })}
      </div>
    </main>
  );
};

export const PreviewPage = () => {
  const [session, setSession] = useState<AdminSession | null>(() => getSession());

  if (!session) {
    return <ConnectGate onConnected={setSession} />;
  }

  return (
    <PreviewWorkbench
      session={session}
      onDisconnect={() => {
        clearSession();
        setSession(null);
      }}
    />
  );
};

export default PreviewPage;
