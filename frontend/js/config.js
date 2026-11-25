// Backend URL resolution (first match wins):
//  1. window.FINCHECK_API_BASE — set it in a <script> before this file for a custom deployment
//     (e.g. a Vercel-hosted frontend talking to a Hugging Face Space backend).
//  2. Served by the backend itself under /ui/ (Docker / HF Spaces) — same origin.
//  3. Local development (python -m http.server on another port, or file://) — http://127.0.0.1:8000.
const API_BASE = (() => {
  if (window.FINCHECK_API_BASE) return String(window.FINCHECK_API_BASE).replace(/\/$/, "");
  if (location.protocol.startsWith("http") && location.pathname.startsWith("/ui")) return location.origin;
  return "http://127.0.0.1:8000";
})();
