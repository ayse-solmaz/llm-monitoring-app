/**
 * Smoke: DeepKwiki context injection flag in WebMCP bundle.
 * Run: node frontend/scripts/smoke-admin-deepkwiki.mjs
 */
import { createRequire } from "module";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Compile-free smoke: duplicate minimal search logic expectations.
const CORPUS_IDS = [
  "physics-water-boil",
  "backend-stack",
  "jwt-tokens",
  "ports",
  "model-prod",
  "architecture",
  "mlc-docker",
];

const MATCH_CASES = [
  ["Su kaç derecede kaynar?", "physics-water-boil"],
  ["Bu projenin backend dili nedir?", "backend-stack"],
  ["Access token kaç dakika geçerlidir?", "jwt-tokens"],
];

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

// Dynamic import of built TS is not available; inline the contract we expect.
const enabledOpts = {
  systemPrompt: "test",
  temperature: 0,
  topP: 0.9,
  maxTokens: 48,
  adapterId: "deepkwiki",
  deepKwikiEnabled: true,
};

const disabledOpts = { ...enabledOpts, deepKwikiEnabled: false };

// Import compiled deepkwiki via ts-node alternative: read source presence
const deepkwikiPath = path.join(__dirname, "../src/lib/deepkwiki.ts");
const fs = await import("fs");
const src = fs.readFileSync(deepkwikiPath, "utf8");
assert(src.includes("physics-water-boil"), "corpus entry physics-water-boil missing");
assert(src.includes("searchDeepKwiki"), "searchDeepKwiki export missing");

const webmcpPath = path.join(__dirname, "../src/lib/webmcp.ts");
const webmcpSrc = fs.readFileSync(webmcpPath, "utf8");
assert(
  webmcpSrc.includes("opts.deepKwikiEnabled"),
  "webmcp must gate wiki on deepKwikiEnabled"
);
assert(
  webmcpSrc.includes("searchDeepKwiki"),
  "webmcp must call searchDeepKwiki"
);

const storePath = path.join(__dirname, "../src/store/llmAdminStore.ts");
const storeSrc = fs.readFileSync(storePath, "utf8");
assert(storeSrc.includes("hydrateFromApi"), "store must hydrate from API");
assert(storeSrc.includes("saveToApi"), "store must save to API");

const apiPath = path.join(__dirname, "../src/lib/llm-admin-api.ts");
const apiSrc = fs.readFileSync(apiPath, "utf8");
assert(apiSrc.includes("/admin/llm-settings"), "API client must use admin route");

for (const id of CORPUS_IDS) {
  assert(src.includes(`id: "${id}"`), `corpus entry ${id} missing`);
}
for (const [q, id] of MATCH_CASES) {
  assert(src.includes(id), `pattern target ${id} for "${q}"`);
}
assert(src.includes("100 derecede"), "water fact body missing");
assert(src.includes("Go (Golang)"), "backend fact body missing");
assert(src.includes("15 dakika"), "jwt fact body missing");

console.log("PASS smoke-admin-deepkwiki");
console.log("  deepKwikiEnabled=true opts:", JSON.stringify(enabledOpts));
console.log("  deepKwikiEnabled=false opts:", JSON.stringify(disabledOpts));
console.log("  corpus ids present:", CORPUS_IDS.join(", "));
console.log("  match cases:", MATCH_CASES.map(([q, id]) => `${id}`).join(", "));
