/**
 * Server-Sent Events reader over fetch
 *
 * EventSource only supports GET, but zone rendering needs a POST body,
 * so the stream endpoint is consumed via fetch + ReadableStream and
 * parsed here. Handles chunk boundaries that split events.
 */

export const readSSEStream = async (
  response: Response,
  onEvent: (event: string, data: any) => void,
): Promise<void> => {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Streaming is not supported in this environment');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let separatorIndex: number;
    while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);

      let eventName = 'message';
      const dataLines: string[] = [];

      for (const line of rawEvent.split('\n')) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trim());
        }
      }

      if (dataLines.length === 0) continue;

      try {
        onEvent(eventName, JSON.parse(dataLines.join('\n')));
      } catch {
        // Malformed event payload: skip, never break the stream
      }
    }
  }
};

export default readSSEStream;
