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
    id = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
          const r = (Math.random() * 16) | 0;
          return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
        });
    sessionStorage.setItem(key, id);
  }
  return id;
}
