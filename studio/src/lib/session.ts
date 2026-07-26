/**
 * Admin sessions for the studio console.
 *
 * Credentials live ONLY in sessionStorage: they never enter the bundle,
 * never persist across browser sessions, and are never sent anywhere but
 * the backend URL the operator typed in.
 */

export interface AdminSession {
  baseUrl: string;
  adminKey: string;
  tenant: string;
}

const STORAGE_KEY = "genui-studio-admin";

interface StoredSessions {
  sessions: AdminSession[];
  active: string;
}

export const sessionId = (session: AdminSession): string =>
  `${session.baseUrl}|${session.tenant}`;

export const sessionLabel = (
  session: AdminSession,
  all: AdminSession[],
): string =>
  all.filter((other) => other.tenant === session.tenant).length > 1
    ? `${session.tenant} @ ${session.baseUrl.replace(/^https?:\/\//i, "")}`
    : session.tenant;

const isSession = (value: unknown): value is AdminSession => {
  const candidate = value as AdminSession | null;
  return (
    typeof candidate?.baseUrl === "string" &&
    typeof candidate?.adminKey === "string" &&
    typeof candidate?.tenant === "string"
  );
};

const read = (): StoredSessions => {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "null");
    const sessions: AdminSession[] = Array.isArray(parsed?.sessions)
      ? parsed.sessions.filter(isSession)
      : [];
    if (!sessions.length) return { sessions: [], active: "" };
    const active = sessions.some((s) => sessionId(s) === parsed?.active)
      ? String(parsed.active)
      : sessionId(sessions[0]);
    return { sessions, active };
  } catch {
    return { sessions: [], active: "" };
  }
};

const write = (state: StoredSessions): void => {
  if (!state.sessions.length) sessionStorage.removeItem(STORAGE_KEY);
  else sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
};

export const listSessions = (): AdminSession[] => read().sessions;

export const getSession = (): AdminSession | null => {
  const { sessions, active } = read();
  return sessions.find((s) => sessionId(s) === active) ?? null;
};

export const saveSession = (session: AdminSession): void => {
  const { sessions } = read();
  write({
    sessions: [
      ...sessions.filter((s) => sessionId(s) !== sessionId(session)),
      session,
    ],
    active: sessionId(session),
  });
};

export const setActiveSession = (id: string): AdminSession | null => {
  const { sessions } = read();
  if (sessions.some((s) => sessionId(s) === id))
    write({ sessions, active: id });
  return getSession();
};

export const clearSession = (): AdminSession | null => {
  const { sessions, active } = read();
  const remaining = sessions.filter((s) => sessionId(s) !== active);
  write({
    sessions: remaining,
    active: remaining[0] ? sessionId(remaining[0]) : "",
  });
  return getSession();
};

export const normalizeBaseUrl = (input: string): string | null => {
  const trimmed = input.trim().replace(/\/+$/, "");
  if (!/^https?:\/\/[^\s]+$/i.test(trimmed)) return null;
  return trimmed;
};
