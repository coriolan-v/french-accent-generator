import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { extname, join, normalize } from "node:path";

const port = Number(process.env.PORT || 4173);
const publicRoot = join(process.cwd(), "public");
const assetsRoot = join(process.cwd(), "assets");
const publicReferences = new Set([
  "1-Worse-French-accent.m4a",
  "2-worste-ref-2.m4a",
  "3-worse-ref-3.m4a",
  "4-worse-reference-15s.m4a",
]);
const MAX_BODY_BYTES = 12 * 1024 * 1024;
const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mp3": "audio/mpeg",
  ".m4a": "audio/mp4",
};

function respondJson(response, status, payload) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(JSON.stringify(payload));
}

async function readBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw Object.assign(new Error("Recording is too large."), { statusCode:413 });
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function engineHealth() {
  try {
    const response = await fetch("http://127.0.0.1:4174/health", { signal:AbortSignal.timeout(800) });
    return response.ok;
  } catch {
    return false;
  }
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host}`);
  if (url.pathname === "/api/health") {
    const ready = await engineHealth();
    return respondJson(response, 200, { engine:ready ? "vevo-ready" : "vevo-offline", uploads:false });
  }
  if (url.pathname === "/api/transform" && request.method === "POST") {
    try {
      if (!(await engineHealth())) return respondJson(response, 503, { error:"The Vevo engine is offline. Start it with npm run engine." });
      const body = await readBody(request);
      const engineResponse = await fetch("http://127.0.0.1:4174/transform", {
        method:"POST",
        headers:{ "content-type":"application/json" },
        body,
        signal:AbortSignal.timeout(300_000),
      });
      const result = await engineResponse.text();
      response.writeHead(engineResponse.status, { "content-type":"application/json; charset=utf-8", "cache-control":"no-store" });
      return response.end(result);
    } catch (error) {
      return respondJson(response, error.statusCode || 500, { error:error.message || "Local accent conversion failed." });
    }
  }
  if (request.method !== "GET") return respondJson(response, 405, { error: "Method not allowed" });

  const assetName = url.pathname.startsWith("/assets/") ? url.pathname.slice(8) : undefined;
  const root = assetName ? assetsRoot : publicRoot;
  const requested = assetName || (url.pathname === "/" ? "/index.html" : url.pathname);
  if (assetName && !publicReferences.has(assetName)) return respondJson(response, 404, { error: "Not found" });
  const safePath = normalize(requested).replace(/^(\.\.[/\\])+/, "");
  const filePath = join(root, safePath);
  if (!filePath.startsWith(root) || !existsSync(filePath)) return respondJson(response, 404, { error: "Not found" });
  response.writeHead(200, {
    "content-type": mimeTypes[extname(filePath)] || "application/octet-stream",
    "cache-control": "no-store",
  });
  response.end(readFileSync(filePath));
});

server.listen(port, "127.0.0.1", () => {
  console.log(`French-O-Matic running at http://127.0.0.1:${port}`);
});
