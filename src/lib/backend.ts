export function getBackendUrl() {
  return process.env.BACKEND_URL ?? "http://localhost:8001";
}

