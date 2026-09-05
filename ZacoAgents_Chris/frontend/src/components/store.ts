/** Reading and writing one remembered preference, without letting the browser break the page.
 *
 * `localStorage` is not always there to be used: a private window, a browser set to block site
 * data, or an embedded view can make the accessor itself throw rather than return nothing. A
 * sidebar that remembers its width is a convenience, so it fails to the default rather than
 * taking the interface down with it.
 */

export function remembered(key: string, fallback: boolean): boolean {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "true";
  } catch {
    return fallback;
  }
}

export function remember(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Nothing to do and nothing worth saying: the preference simply does not survive the tab.
  }
}
