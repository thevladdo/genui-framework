/**
 * Segment preview (admin): compose audiences, render one zone config
 * live against /zone/render, and compare what each segment is served.
 */

import { useEffect, useState } from 'react';
import studioStyles from '../studio/Studio.module.css';
import measureStyles from '../measure/Measure.module.css';
import styles from './Preview.module.css';
import { backendHealth } from '../../lib/api';
import type { RenderProfile } from '../../lib/segment';
import { getSession, sessionId, type AdminSession } from '../../lib/session';
import { ConnectGate } from '../studio/ConnectGate';
import { ConsoleHeader } from '../studio/ConsoleHeader';
import { AgentPromptModal } from './AgentPromptModal';
import { AudienceMatrix } from './AudienceMatrix';

const PINNED_PLACEHOLDER = `[
  { "type": "link", "url": "https://example.com/pricing", "title": "See pricing" }
]`;

const PreviewWorkbench = ({
  session,
  onSession,
}: {
  session: AdminSession;
  onSession: (next: AdminSession | null) => void;
}) => {
  const [zoneId, setZoneId] = useState('studio-preview');
  const [basePrompt, setBasePrompt] = useState(
    'Curate this zone for the audience: pick the components and copy that will resonate most.',
  );
  const [contextPrompt, setContextPrompt] = useState('Homepage, above the fold.');
  const [pinnedJson, setPinnedJson] = useState(PINNED_PLACEHOLDER);
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);
  const [agentOpen, setAgentOpen] = useState(false);

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

  const buildPayload = (profile: RenderProfile): Record<string, unknown> => {
    if (!zoneId.trim()) {
      throw new Error('Enter a zone_id.');
    }

    let pinned: unknown = [];
    const rawPinned = pinnedJson.trim();
    if (rawPinned) {
      try {
        pinned = JSON.parse(rawPinned);
      } catch {
        throw new Error('Pinned content is not valid JSON. Expected an array (or leave it empty).');
      }
      if (!Array.isArray(pinned)) {
        throw new Error('Pinned content must be a JSON array of pinned items.');
      }
    }

    return {
      zone_id: zoneId.trim(),
      base_prompt: basePrompt,
      context_prompt: contextPrompt || null,
      pinned_content: pinned,
      cache_strategy: 'live',
      ...profile,
    };
  };

  return (
    <main className={studioStyles.page} style={{ marginTop: '3rem' }}>
      <ConsoleHeader session={session} onSession={onSession} />

      <section className={`st-glass ${studioStyles.testerCard}`}>
        <div className={styles.configHead}>
          <h2 className="st-section-title">Zone config</h2>
          <button
            type="button"
            className={styles.agentTrigger}
            onClick={() => setAgentOpen(true)}
          >
            Draft with an AI assistant
          </button>
        </div>
        <p className={studioStyles.testerSub}>
          The prompt and pinned content a page would ship for this zone.
          Every audience below is rendered live against this exact config.
        </p>

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

        {llmConfigured === false && (
          <p className={styles.warnBanner} role="alert">
            This backend reports no configured LLM engine (/health: llm
            unconfigured). Renders will degrade to the pinned-only
            fallback until LLM_PROVIDER and its key or base URL are set.
          </p>
        )}
      </section>

      <AudienceMatrix session={session} buildPayload={buildPayload} />

      {agentOpen && <AgentPromptModal onClose={() => setAgentOpen(false)} />}
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
      key={sessionId(session)}
      session={session}
      onSession={setSession}
    />
  );
};

export default PreviewPage;
