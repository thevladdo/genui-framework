/**
 * Tests for the tenant scoping of the console (lib/session.ts + lib/api.ts):
 * which session is active, and that a call carries exactly that tenant's key.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

// sessionStorage is a browser global; the store below is the whole dependency.
const stored = new Map();
globalThis.sessionStorage = {
  getItem: (key) => (stored.has(key) ? stored.get(key) : null),
  setItem: (key, value) => stored.set(key, String(value)),
  removeItem: (key) => stored.delete(key),
};

const {
  clearSession,
  getSession,
  listSessions,
  saveSession,
  sessionId,
  sessionLabel,
  setActiveSession,
} = require("./.build/session.js");
const {
  deleteDocument,
  listDocuments,
  listZoneConfigs,
  saveTenantTheme,
  verifySession,
} = require("./.build/api.js");

const ACME = { baseUrl: "http://localhost:8000", adminKey: "sk_a", tenant: "acme" };
const GLOBEX = { baseUrl: "http://localhost:8000", adminKey: "sk_g", tenant: "globex" };

const reset = () => {
  stored.clear();
};

// Active session

test("no session at all", () => {
  reset();
  assert.equal(getSession(), null);
  assert.deepEqual(listSessions(), []);
});

test("connecting a tenant makes it the active one", () => {
  reset();
  saveSession(ACME);
  saveSession(GLOBEX);
  assert.deepEqual(getSession(), GLOBEX);
  assert.equal(listSessions().length, 2);
});

test("switching picks the other connected session, key included", () => {
  reset();
  saveSession(ACME);
  saveSession(GLOBEX);
  assert.deepEqual(setActiveSession(sessionId(ACME)), ACME);
  assert.deepEqual(getSession(), ACME);
  assert.deepEqual(setActiveSession("http://nope|ghost"), ACME);
});

test("reconnecting a tenant replaces its key instead of duplicating it", () => {
  reset();
  saveSession(ACME);
  saveSession({ ...ACME, adminKey: "sk_rotated" });
  assert.equal(listSessions().length, 1);
  assert.equal(getSession().adminKey, "sk_rotated");
});

test("same tenant name on two backends stays two sessions", () => {
  reset();
  const staging = { ...ACME, baseUrl: "http://staging:8000" };
  saveSession(ACME);
  saveSession(staging);
  const all = listSessions();
  assert.equal(all.length, 2);
  assert.equal(sessionLabel(ACME, all), "acme @ localhost:8000");
  assert.equal(sessionLabel(GLOBEX, [GLOBEX]), "globex");
});

test("disconnecting hands over to another connected tenant", () => {
  reset();
  saveSession(ACME);
  saveSession(GLOBEX);
  assert.deepEqual(clearSession(), ACME);
  assert.equal(clearSession(), null);
  assert.equal(sessionStorage.getItem("genui-studio-admin"), null);
});

test("a session stored by an older build is dropped, not half read", () => {
  reset();
  sessionStorage.setItem(
    "genui-studio-admin",
    JSON.stringify({ baseUrl: "http://localhost:8000", adminKey: "sk_a" }),
  );
  assert.equal(getSession(), null);
  sessionStorage.setItem("genui-studio-admin", "{not json");
  assert.equal(getSession(), null);
});

// Scoping: the call carries the active tenant's key

const captureFetch = () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, key: init.headers["X-API-Key"] });
    return { ok: true, json: async () => ({ zones: [], storage: "redis" }) };
  };
  return calls;
};

test("a call is made with the active tenant's key", async () => {
  reset();
  saveSession(ACME);
  saveSession(GLOBEX);
  const calls = captureFetch();

  await listZoneConfigs(getSession());
  setActiveSession(sessionId(ACME));
  await listZoneConfigs(getSession());

  assert.deepEqual(
    calls.map((c) => c.key),
    ["sk_g", "sk_a"],
  );
  assert.ok(calls[0].url.startsWith("http://localhost:8000/api/v1/zone/config"));
});

test("a stale session is refused instead of writing to the wrong tenant", async () => {
  reset();
  saveSession(ACME);
  saveSession(GLOBEX);
  const stale = getSession();
  captureFetch();

  setActiveSession(sessionId(ACME));
  await assert.rejects(() => listZoneConfigs(stale), /no longer the active session/);

  clearSession();
  clearSession();
  await assert.rejects(() => listZoneConfigs(ACME), /no longer the active session/);
});


const heldFetch = () => {
  const held = [];
  globalThis.fetch = (url, init) =>
    new Promise((resolve) => held.push({ url, init, resolve }));
  return held;
};

const reply = (status, body) => ({
  ok: status < 400,
  status,
  json: async () => body,
});

const SETTLED = "settled";
const PENDING = "pending";

const outcome = (promise) =>
  Promise.race([
    promise.then(() => SETTLED, () => SETTLED),
    new Promise((resolve) => setTimeout(() => resolve(PENDING), 20)),
  ]);

test("a response that lands after a tenant switch is dropped", async () => {
  reset();
  saveSession(GLOBEX);
  saveSession(ACME);
  const held = heldFetch();

  const late = listDocuments(ACME);
  setActiveSession(sessionId(GLOBEX));
  const current = listDocuments(GLOBEX);
  held[1].resolve(reply(200, { documents: [{ source_document: "g.pdf", chunks: 1 }] }));
  held[0].resolve(reply(200, { documents: [{ source_document: "a.pdf", chunks: 1 }] }));

  assert.deepEqual((await current).documents.map((d) => d.source_document), ["g.pdf"]);
  assert.equal(await outcome(late), PENDING);
});

test("an error that lands after a tenant switch is dropped, not raised", async () => {
  reset();
  saveSession(GLOBEX);
  saveSession(ACME);
  const held = heldFetch();

  const late = listDocuments(ACME);
  setActiveSession(sessionId(GLOBEX));
  held[0].resolve(reply(401, { detail: "Invalid API key" }));

  assert.equal(await outcome(late), PENDING);
  assert.deepEqual(getSession(), GLOBEX);
  assert.equal(listSessions().length, 2);
});

test("a reply for the tenant still active is delivered, errors included", async () => {
  reset();
  saveSession(ACME);
  const held = heldFetch();

  const failing = listDocuments(ACME);
  held[0].resolve(reply(500, { detail: "boom" }));
  await assert.rejects(failing, /boom/);
});

test("a delete started from the tenant just left is refused", async () => {
  reset();
  saveSession(GLOBEX);
  saveSession(ACME);
  const listedBy = getSession();
  const held = heldFetch();

  setActiveSession(sessionId(GLOBEX));
  await assert.rejects(
    () => deleteDocument(listedBy, "shared-name.pdf"),
    /tenant "acme", which is no longer the active session/,
  );
  assert.equal(held.length, 0);
});

test("a theme save follows the same rule", async () => {
  reset();
  saveSession(GLOBEX);
  saveSession(ACME);
  const held = heldFetch();

  const inFlight = saveTenantTheme(ACME, { accent: "#ff0000" });
  setActiveSession(sessionId(GLOBEX));
  held[0].resolve(reply(200, { theme: { accent: "#ff0000" }, updated_at: "now", storage: "redis" }));
  assert.equal(await outcome(inFlight), PENDING);

  await assert.rejects(
    () => saveTenantTheme(ACME, { accent: "#00ff00" }),
    /no longer the active session/,
  );
  assert.equal(held.length, 1);
  assert.equal(held[0].init.headers["X-API-Key"], "sk_a");
});

test("verifying a key is the one call made before any session exists", async () => {
  reset();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ tenant: "acme", is_admin: true }),
  });
  const identity = await verifySession({
    baseUrl: "http://localhost:8000",
    adminKey: "sk_a",
  });
  assert.equal(identity.tenant, "acme");
});
