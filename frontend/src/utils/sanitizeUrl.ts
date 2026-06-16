/**
 * URL sanitization (defense in depth)
 *
 * The backend already enforces a URL whitelist on generated components,
 * but rendered hrefs are the last line of defense: anything with a
 * dangerous scheme is dropped here regardless of where it came from.
 */

const DANGEROUS_SCHEMES = ['javascript:', 'data:', 'vbscript:', 'file:', 'blob:'];
const SAFE_SCHEMES = ['http://', 'https://', 'mailto:', 'tel:'];

/**
 * Returns the URL if it is safe to use as an href/src, undefined otherwise.
 * Allows http(s), mailto, tel, and relative URLs (/path, #anchor, ?query).
 */
export const sanitizeUrl = (url: string | undefined | null): string | undefined => {
  if (!url) return undefined;

  const trimmed = url.trim();
  if (!trimmed) return undefined;

  // Strip whitespace and hyphens before the scheme check to catch
  // obfuscations like "java\tscript:" or "java-script:"
  const lowered = trimmed.toLowerCase().replace(/[\s-]/g, '');

  if (DANGEROUS_SCHEMES.some(scheme => lowered.startsWith(scheme))) {
    return undefined;
  }

  // Relative URLs are fine
  if (trimmed.startsWith('/') || trimmed.startsWith('#') || trimmed.startsWith('?')) {
    return trimmed;
  }

  // Scheme-relative or absolute: must be a known-safe scheme
  if (SAFE_SCHEMES.some(scheme => lowered.startsWith(scheme))) {
    return trimmed;
  }

  // Bare paths without scheme ("products/x") are allowed; anything with
  // an unknown scheme ("custom:...") is not.
  if (!lowered.includes(':')) {
    return trimmed;
  }

  return undefined;
};

export default sanitizeUrl;
