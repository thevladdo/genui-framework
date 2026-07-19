/**
 * Minimal hash router.
 */

import { useCallback, useEffect, useState } from "react";

export type RoutePath = "/" | "/playground" | "/studio" | "/measure" | "/about";

export interface HashRoute {
  path: RoutePath;
  query: string;
}

const parseHash = (): HashRoute => {
  const hash = window.location.hash.replace(/^#/, "") || "/";
  const [rawPath, query = ""] = hash.split("?");
  const path: RoutePath =
    rawPath === "/playground" ||
      rawPath === "/studio" ||
      rawPath === "/measure" ||
      rawPath === "/about"
      ? rawPath
      : "/";
  return { path, query };
};

export const useHashRoute = (): HashRoute & {
  navigate: (path: RoutePath, query?: string) => void;
  replaceQuery: (query: string) => void;
} => {
  const [route, setRoute] = useState<HashRoute>(parseHash);

  useEffect(() => {
    const onHashChange = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((path: RoutePath, query = "") => {
    window.location.hash = query ? `${path}?${query}` : path;
  }, []);

  // Keeps the share link in sync while sliding controls without
  // flooding the browser history
  const replaceQuery = useCallback((query: string) => {
    const { path } = parseHash();
    const hash = query ? `#${path}?${query}` : `#${path}`;
    window.history.replaceState(null, "", hash);
    setRoute({ path, query });
  }, []);

  return { ...route, navigate, replaceQuery };
};
