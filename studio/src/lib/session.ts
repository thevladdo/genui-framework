/**
 * Admin session for the Content Studio.
 *
 * Credentials live ONLY in sessionStorage: they never enter the bundle,
 * never persist across browser sessions, and are never sent anywhere but
 * the backend URL the operator typed in.
 */

export interface AdminSession {
  baseUrl: string;
  adminKey: string;
}

const STORAGE_KEY = "genui-studio-admin";

export const getSession = (): AdminSession | null => {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      typeof parsed?.baseUrl === "string" &&
      typeof parsed?.adminKey === "string"
    ) {
      return { baseUrl: parsed.baseUrl, adminKey: parsed.adminKey };
    }
  } catch {
    // Corrupt storage treat as no session
  }
  return null;
};

export const saveSession = (session: AdminSession): void => {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
};

export const clearSession = (): void => {
  sessionStorage.removeItem(STORAGE_KEY);
};

export const normalizeBaseUrl = (input: string): string | null => {
  const trimmed = input.trim().replace(/\/+$/, "");
  if (!/^https?:\/\/[^\s]+$/i.test(trimmed)) return null;
  return trimmed;
};
