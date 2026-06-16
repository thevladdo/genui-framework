/**
 * GenUI event emission
 *
 * Sends impression/click events to the backend events endpoint,
 * closing the measurement loop (uplift vs control arm).
 *
 * Fire-and-forget: events must never break or slow down the host app.
 */

export interface GenUIEvent {
  /** impression | click | custom snake_case type */
  event_type: string;
  zone_id: string;
  /** Identity of the generated variant (meta.renderId) */
  render_id?: string;
  /** Experiment arm (meta.experiment.arm) */
  arm?: string;
  segment?: string;
  item_title?: string;
  item_url?: string;
  user_id?: string;
  ts?: string;
}

/**
 * Send a batch of events. Uses keepalive so events survive navigation
 * (e.g. a click immediately followed by a page change).
 */
export const sendGenUIEvents = (
  apiUrl: string,
  apiKey: string | undefined,
  events: GenUIEvent[],
): void => {
  if (!events.length || typeof fetch === 'undefined') return;

  try {
    fetch(`${apiUrl}/api/v1/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      },
      body: JSON.stringify({ events }),
      keepalive: true,
    }).catch(() => {
      /* best effort */
    });
  } catch {
    /* best effort */
  }
};

export default sendGenUIEvents;
