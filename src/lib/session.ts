/**
 * Per-tab session isolation.
 * Each browser tab gets a unique session ID stored in sessionStorage,
 * so conversations are scoped to the tab that created them.
 */
export function getSessionId(): string {
  if (typeof window === "undefined") return "";

  const key = "agenticstack_session_id";
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(key, id);
  }
  return id;
}
