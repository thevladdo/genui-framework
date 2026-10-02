const INTRO_KEY = "genui.intro.seen";

export const shouldShowIntro = (): boolean => {
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches)
    return false;
  try {
    return localStorage.getItem(INTRO_KEY) !== "1";
  } catch {
    return true;
  }
};

export const markIntroSeen = (): void => {
  try {
    localStorage.setItem(INTRO_KEY, "1");
  } catch {
    // Private browsing: the intro will show again next visit.
  }
};
