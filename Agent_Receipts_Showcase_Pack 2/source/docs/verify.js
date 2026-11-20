/* Verifies an Agent Receipts ledger. Same rules as `receipts verify`. Runs in the browser and in Node. */
(function (root) {
  "use strict";
  var GENESIS = "0".repeat(64);

  // Canonical JSON, byte-for-byte what the Python side hashes: sorted keys, no spaces, UTF-8.
  function canon(v) {
    if (v === null) return "null";
    if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
    if (typeof v === "object") {
      return "{" + Object.keys(v).sort().map(function (k) {
        return JSON.stringify(k) + ":" + canon(v[k]);
      }).join(",") + "}";
    }
    return JSON.stringify(v);
  }

  async function sha256(text) {
    var subtle = (root.crypto && root.crypto.subtle) || require("crypto").webcrypto.subtle;
    var buf = await subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
  }

  async function verifyText(text) {
    var lines = text.split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    var prev = GENESIS, expectedSeq = 0, count = 0, firstSeq = null, firstPrev = null, checkpoints = [];

    function fail(line, reason, seq) {
      return { ok: false, count: count, head: prev, line: line, seq: seq === undefined ? null : seq, reason: reason };
    }

    for (var i = 0; i < lines.length; i++) {
      var n = i + 1, r;
      if (!lines[i].trim()) return fail(n, "blank line inside ledger");
      try { r = JSON.parse(lines[i]); } catch (e) { return fail(n, "line is not a valid receipt"); }
      if (!r || typeof r !== "object" || r.hash === undefined || r.seq === undefined || r.prev === undefined) {
        return fail(n, "line is not a valid receipt");
      }
      var body = Object.assign({}, r);
      delete body.hash;
      if ((await sha256(canon(body))) !== r.hash) return fail(n, "hash mismatch: receipt content was changed", r.seq);
      if (count === 0) {
        firstSeq = r.seq; firstPrev = r.prev;
        if (r.seq === 0 && r.prev !== GENESIS) return fail(n, "first receipt does not start at genesis", r.seq);
      } else {
        if (r.prev !== prev) return fail(n, "chain broken: prev does not match the previous receipt", r.seq);
        if (r.seq !== expectedSeq) return fail(n, "sequence gap or reorder", r.seq);
      }
      if (r.kind === "checkpoint" && r.meta && typeof r.meta === "object") checkpoints.push(r.meta);
      prev = r.hash; expectedSeq = r.seq + 1; count++;
    }
    if (count && firstSeq > 0) {
      var anchored = checkpoints.some(function (c) {
        return c.pruned_through_seq === firstSeq - 1 && c.pruned_head === firstPrev;
      });
      if (!anchored) return fail(1, "ledger starts after genesis with no matching retention checkpoint", firstSeq);
    }
    return { ok: true, count: count, head: prev };
  }

  var api = { verifyText: verifyText, canon: canon };
  root.AgentReceiptsVerify = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
