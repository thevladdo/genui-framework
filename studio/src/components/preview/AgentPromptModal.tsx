/**
 * The brief for an outside (personal) AI assistant.
 */

import { useEffect, useRef, useState } from 'react';
import { BUILTIN_TYPES } from 'genui-framework';
import studioStyles from '../studio/Studio.module.css';
import styles from './Preview.module.css';
import { AGENTS, agentUrl, buildAgentPrompt, prefills, type AgentTarget } from '../../lib/agentPrompt';
import { isLightColor } from '../../lib/theme';

const copy = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

export const AgentPromptModal = ({ onClose }: { onClose: () => void }) => {
  const [status, setStatus] = useState<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const prompt = buildAgentPrompt(BUILTIN_TYPES);

  useEffect(() => {
    dialog.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const hand = async (agent: AgentTarget) => {
    const copied = await copy(prompt);
    window.open(agentUrl(agent, prompt), '_blank', 'noopener,noreferrer');
    setStatus(
      prefills(agent, prompt)
        ? `${agent.name} opened with the brief in the box.${copied ? ' It is on your clipboard too.' : ''}`
        : copied
          ? `${agent.name} opened. The brief is on your clipboard: paste it in the chat.`
          : `${agent.name} opened. Copy the brief below and paste it in the chat.`,
    );
  };

  return (
    <div
      className={studioStyles.gateOverlay}
      role="dialog"
      aria-modal="true"
      aria-label="Draft this config with an assistant"
      onClick={onClose}
    >
      <div
        className={`st-glass ${styles.agentModal}`}
        ref={dialog}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={styles.agentHead}>
          <h2 className="st-section-title">Draft this config with an assistant</h2>
          <button
            type="button"
            className={styles.removeBtn}
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <p className={studioStyles.testerSub}>
          A realistic zone config is a business, an account state and a dozen
          image URLs that actually resolve. Rather than invent them here, hand
          the brief below to an assistant: it asks whether to build around your
          real site or an invented one, then answers with the four fields ready
          to paste back into this page. The audiences stay yours: they are the
          columns below, and the same config is rendered against each.
        </p>

        <div className={styles.agentGrid}>
          {AGENTS.map((agent) => (
            <button
              key={agent.id}
              type="button"
              className={styles.agentButton}
              style={{
                background: agent.color,
                color: isLightColor(agent.color) ? '#0a0a0c' : '#ffffff',
              }}
              onClick={() => void hand(agent)}
            >
              <span className={styles.agentName}>{agent.name}</span>
              <span className={styles.agentNote}>
                {prefills(agent, prompt) ? 'opens with the brief' : 'copy and paste'}
              </span>
            </button>
          ))}
        </div>

        {status && (
          <p className={styles.agentStatus} role="status">
            {status}
          </p>
        )}

        <label className={studioStyles.fieldLabel} htmlFor="agent-brief">
          The brief
        </label>
        <textarea
          id="agent-brief"
          className={`${studioStyles.field} ${styles.agentBrief}`}
          value={prompt}
          readOnly
          spellCheck={false}
          onFocus={(event) => event.currentTarget.select()}
        />

        <div className={styles.agentActions}>
          <button
            type="button"
            className={studioStyles.primaryButton}
            onClick={async () => {
              setStatus(
                (await copy(prompt))
                  ? 'Brief copied.'
                  : 'Could not reach the clipboard: select the text above and copy it.',
              );
            }}
          >
            Copy the brief
          </button>
        </div>
      </div>
    </div>
  );
};

export default AgentPromptModal;
