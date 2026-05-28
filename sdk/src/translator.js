/**
 * AI Translation SDK — live in-place webpage translation.
 *
 * Drop this file into a page, point a Translator at the API, and existing
 * DOM text (plus a curated set of attributes — alt, title, placeholder,
 * meta description, og:title, og:description) gets swapped in place to the
 * target language. Nothing has to be re-rendered; the browser sees only
 * `nodeValue` mutations on existing text nodes.
 *
 * Design choices worth knowing:
 *
 * - **Text nodes, not elements.** A TreeWalker yields raw text nodes so we
 *   can preserve inline markup (links, bold, etc.) without sending the
 *   whole element through the translator.
 *
 * - **Block-aware grouping.** Adjacent text nodes inside the same block
 *   element (P, LI, H1...) are kept together when batching so the LLM sees
 *   each sentence with its actual surrounding context.
 *
 * - **Viewport priority.** Visible text gets translated first, off-screen
 *   text follows. The user sees their first translated word in a fraction
 *   of the time a top-to-bottom walk would take.
 *
 * - **Two-tier cache.** An in-memory LRU (fast, per-tab) backed by
 *   localStorage (persists across reloads). Both tiers fall through
 *   silently to the server on miss; localStorage write failures
 *   (private mode, quota) never crash translation.
 *
 * - **No build step.** ES2020 module-free script. ``<script src="...">``
 *   it from any page; the global is the ``Translator`` class.
 */

(function (global) {
  "use strict";

  // ---- Constants ----------------------------------------------------------

  // Tags whose textual content is code / typed input / styling — translating
  // them would break the page.
  const SKIP_TAGS = new Set([
    "SCRIPT",
    "STYLE",
    "CODE",
    "PRE",
    "KBD",
    "SAMP",
    "TEXTAREA",
    "NOSCRIPT",
  ]);

  // Attributes we DO want to translate, by element type. Keeping the map
  // explicit (rather than translating every attribute on every element)
  // prevents accidentally rewriting an ``href`` or a ``src`` URL.
  const TRANSLATABLE_ATTRS_BY_TAG = {
    IMG: ["alt", "title"],
    INPUT: ["placeholder", "title", "alt"],
    TEXTAREA: ["placeholder", "title"],
    A: ["title"],
    BUTTON: ["title"],
    META: [], // handled specially — see collectMetaTargets
  };

  // Meta names / og properties whose content is user-visible (search results,
  // social preview) — these need translation even though they never render
  // in the page body.
  const META_PROPERTIES_TO_TRANSLATE = new Set([
    "og:title",
    "og:description",
  ]);
  const META_NAMES_TO_TRANSLATE = new Set([
    "description",
    "twitter:title",
    "twitter:description",
  ]);

  // Limit a single batch to something the API enjoys. ``MAX_BATCH_ITEMS``
  // matches the server's BatchTranslateRequest ``max_length=100`` (we use
  // 50 as a safety margin); ``MAX_BATCH_CHARS`` caps prompt size so a
  // single very long batch can't OOM the LLM context.
  const MAX_BATCH_ITEMS = 50;
  const MAX_BATCH_CHARS = 4000;

  // Memory cache size — 1000 entries is plenty for a typical landing page
  // and well below the cost where the LRU eviction itself becomes notable.
  const MEMORY_CACHE_SIZE = 1000;

  // localStorage namespace. Keeping it short saves bytes per entry across
  // potentially thousands of cached translations.
  const STORAGE_PREFIX = "tr:";

  // ---- ClientCache --------------------------------------------------------

  /**
   * Two-tier translation cache: in-memory LRU + localStorage.
   *
   * Keys are derived from `(profile_slug, target_lang, source_text)`. The
   * profile version is folded in at construction so a profile bump (server-
   * side cache invalidation) automatically translates to a new client key
   * — old localStorage entries stay around but go unreachable.
   *
   * All failure modes (no localStorage, JSON parse error, quota exceeded)
   * degrade silently to a miss — the page should keep working even when
   * the browser refuses to persist anything.
   */
  class ClientCache {
    constructor({ version = "0", maxMemory = MEMORY_CACHE_SIZE } = {}) {
      this.version = String(version);
      this.maxMemory = maxMemory;
      // Map preserves insertion order, which we use as LRU age.
      this.memory = new Map();
    }

    _key(sourceText, targetLang, profileSlug) {
      // djb2 hash — non-cryptographic, very small, collision-resistant
      // enough for a cache key (worst case is a single mis-hit that
      // re-translates one string).
      const payload = `${this.version}|${profileSlug}|${targetLang}|${sourceText}`;
      let h = 5381;
      for (let i = 0; i < payload.length; i++) {
        h = (h * 33) ^ payload.charCodeAt(i);
      }
      // >>> 0 normalises to an unsigned 32-bit integer before base-36.
      return STORAGE_PREFIX + (h >>> 0).toString(36);
    }

    get(sourceText, targetLang, profileSlug) {
      const key = this._key(sourceText, targetLang, profileSlug);
      if (this.memory.has(key)) {
        const val = this.memory.get(key);
        // Re-insert so the most-recently-used entry sits at the back of
        // the Map. Eviction always removes the oldest (front-most).
        this.memory.delete(key);
        this.memory.set(key, val);
        return val;
      }
      try {
        const raw = global.localStorage && global.localStorage.getItem(key);
        if (raw !== null && raw !== undefined) {
          this._setMemory(key, raw);
          return raw;
        }
      } catch (e) {
        // localStorage unavailable (private mode, denied by user, quota
        // exceeded on read). Silent fallthrough to "miss".
      }
      return null;
    }

    set(sourceText, targetLang, profileSlug, translation) {
      const key = this._key(sourceText, targetLang, profileSlug);
      this._setMemory(key, translation);
      try {
        if (global.localStorage) {
          global.localStorage.setItem(key, translation);
        }
      } catch (e) {
        // QuotaExceededError or similar — we keep the memory copy.
      }
    }

    _setMemory(key, val) {
      if (this.memory.has(key)) this.memory.delete(key);
      this.memory.set(key, val);
      if (this.memory.size > this.maxMemory) {
        // Evict the oldest entry. ``keys().next().value`` is O(1).
        const oldest = this.memory.keys().next().value;
        this.memory.delete(oldest);
      }
    }
  }

  // ---- Translator ---------------------------------------------------------

  class Translator {
    /**
     * @param {Object} config
     * @param {string} config.apiUrl       Base URL of the translation API.
     * @param {string} config.targetLang   ISO code, e.g. "id".
     * @param {string} config.profileSlug  Profile to translate under.
     * @param {string} [config.sourceLang] Optional; omit to auto-detect.
     * @param {string} [config.token]      Optional bearer token (future auth).
     * @param {boolean} [config.debug]     Log progress / stats to the console.
     */
    constructor(config) {
      if (!config || !config.apiUrl) throw new Error("apiUrl is required");
      if (!config.targetLang) throw new Error("targetLang is required");
      if (!config.profileSlug) throw new Error("profileSlug is required");

      this.apiUrl = config.apiUrl.replace(/\/$/, "");
      this.targetLang = config.targetLang;
      this.profileSlug = config.profileSlug;
      this.sourceLang = config.sourceLang || null;
      this.token = config.token || null;
      this.debug = Boolean(config.debug);

      // Profile version is fetched lazily on first use — we don't want the
      // constructor to be async. Until it arrives the cache uses "0" and
      // simply repopulates once the real version returns.
      this.profileVersion = "0";
      this.cache = new ClientCache({ version: this.profileVersion });

      this._mutationObserver = null;
      // Throttle mutation-driven re-translation. ``debounceMs`` collapses
      // bursts of DOM changes (e.g. a SPA route render) into one translate
      // pass.
      this._mutationTimer = null;
      this.debounceMs = 250;

      this._log("Translator initialized", {
        target: this.targetLang,
        profile: this.profileSlug,
        source: this.sourceLang || "auto",
      });
    }

    _log(...args) {
      if (this.debug || global.localStorage?.getItem("tr:debug") === "1") {
        console.log("[Translator]", ...args);
      }
    }

    async _fetchProfileVersion() {
      try {
        const resp = await fetch(
          `${this.apiUrl}/profiles/${encodeURIComponent(this.profileSlug)}`,
          { headers: this._headers() }
        );
        if (resp.ok) {
          const profile = await resp.json();
          if (profile && profile.version !== undefined) {
            this.profileVersion = String(profile.version);
            this.cache = new ClientCache({ version: this.profileVersion });
            this._log("profile version fetched", this.profileVersion);
          }
        }
      } catch (e) {
        // Soft failure — we'll just keep using version "0" which means the
        // client cache is unreachable across reloads; server still serves
        // correct content from its own cache.
        this._log("could not fetch profile version", e);
      }
    }

    _headers() {
      const h = { "Content-Type": "application/json" };
      if (this.token) h["Authorization"] = `Bearer ${this.token}`;
      return h;
    }

    // ---- collection -----------------------------------------------------

    /**
     * Walk the DOM and yield translation targets.
     *
     * Returns an array of ``{ id, text, source, blockKey }`` where ``source``
     * is either ``{ kind: "text", node }`` for a DOM text node or
     * ``{ kind: "attr", element, attr }`` for a translatable attribute.
     */
    collectTextNodes(root) {
      root = root || document.body;
      const targets = [];
      let counter = 0;

      // ---- attribute targets ----
      const collectAttrTargets = (el) => {
        const tag = el.tagName;
        const attrs = TRANSLATABLE_ATTRS_BY_TAG[tag];
        if (attrs && attrs.length) {
          for (const attr of attrs) {
            const val = el.getAttribute(attr);
            if (val && val.trim()) {
              targets.push({
                id: `t${counter++}`,
                text: val,
                source: { kind: "attr", element: el, attr },
                blockKey: this._blockKey(el),
              });
            }
          }
        }
      };

      // ---- text-node walker ----
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => {
          let parent = node.parentElement;
          while (parent) {
            if (SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
            if (parent.hasAttribute("data-no-translate"))
              return NodeFilter.FILTER_REJECT;
            if (parent.getAttribute("translate") === "no")
              return NodeFilter.FILTER_REJECT;
            if (parent.hasAttribute("data-translated"))
              return NodeFilter.FILTER_REJECT;
            parent = parent.parentElement;
          }
          if (!node.nodeValue || !node.nodeValue.trim()) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      });

      let node;
      while ((node = walker.nextNode())) {
        targets.push({
          id: `t${counter++}`,
          text: node.nodeValue.trim(),
          source: { kind: "text", node, originalLeading: node.nodeValue.match(/^\s*/)[0], originalTrailing: node.nodeValue.match(/\s*$/)[0] },
          blockKey: this._blockKey(node.parentElement),
        });
      }

      // Now sweep elements for attributes — done separately because the
      // text-walker can't yield attribute hits.
      const elementWalker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, {
        acceptNode: (el) => {
          if (SKIP_TAGS.has(el.tagName)) return NodeFilter.FILTER_REJECT;
          if (el.hasAttribute("data-no-translate")) return NodeFilter.FILTER_REJECT;
          if (el.getAttribute("translate") === "no") return NodeFilter.FILTER_REJECT;
          if (TRANSLATABLE_ATTRS_BY_TAG[el.tagName]) return NodeFilter.FILTER_ACCEPT;
          return NodeFilter.FILTER_SKIP;
        },
      });
      let el;
      while ((el = elementWalker.nextNode())) {
        collectAttrTargets(el);
      }

      // ---- meta tags (separate handling — they live in <head>) ----
      const metaTargets = this._collectMetaTargets(counter);
      counter += metaTargets.length;
      targets.push(...metaTargets);

      return targets;
    }

    _collectMetaTargets(startCounter) {
      const out = [];
      const head = document.head;
      if (!head) return out;
      let counter = startCounter;
      for (const meta of head.querySelectorAll("meta")) {
        if (meta.hasAttribute("data-no-translate")) continue;
        const property = meta.getAttribute("property");
        const name = meta.getAttribute("name");
        const isTarget =
          (property && META_PROPERTIES_TO_TRANSLATE.has(property)) ||
          (name && META_NAMES_TO_TRANSLATE.has(name));
        if (!isTarget) continue;
        const content = meta.getAttribute("content");
        if (!content || !content.trim()) continue;
        out.push({
          id: `t${counter++}`,
          text: content,
          source: { kind: "attr", element: meta, attr: "content" },
          blockKey: "__meta__",
        });
      }
      return out;
    }

    _blockKey(element) {
      // Walk up until we find a block-level element; key by its tag + an
      // assigned index so adjacent text in the same paragraph stays grouped.
      // We tag the block once with ``data-tr-block`` so the same paragraph
      // doesn't get a different key on each call.
      const BLOCK_TAGS = new Set([
        "P", "LI", "H1", "H2", "H3", "H4", "H5", "H6",
        "BLOCKQUOTE", "TD", "TH", "DT", "DD", "FIGCAPTION",
        "ARTICLE", "SECTION", "ASIDE", "DIV",
      ]);
      let e = element;
      while (e && !BLOCK_TAGS.has(e.tagName)) e = e.parentElement;
      if (!e) return "__root__";
      if (!e.dataset.trBlock) {
        e.dataset.trBlock = String(Math.random()).slice(2, 10);
      }
      return e.dataset.trBlock;
    }

    // ---- batching -------------------------------------------------------

    /**
     * Pack targets into batches honouring the API's per-request cap.
     *
     * Greedy bin-packing: walk the targets in source order, start a new
     * batch when adding the next item would exceed the count OR char limit.
     * We keep each block contiguous in a single batch when possible (a
     * block break is preferred over a mid-block split).
     */
    batchGroups(targets, { maxItems = MAX_BATCH_ITEMS, maxChars = MAX_BATCH_CHARS } = {}) {
      const batches = [];
      let current = [];
      let currentChars = 0;
      let currentBlock = null;

      const flush = () => {
        if (current.length) batches.push(current);
        current = [];
        currentChars = 0;
        currentBlock = null;
      };

      for (const t of targets) {
        const len = t.text.length;
        const overflow =
          current.length + 1 > maxItems || currentChars + len > maxChars;
        // Prefer to cut on a block boundary unless we're at the very start.
        const blockChange = current.length && t.blockKey !== currentBlock;
        if (overflow || (blockChange && currentChars > maxChars * 0.7)) {
          flush();
        }
        current.push(t);
        currentChars += len;
        currentBlock = t.blockKey;
      }
      flush();
      return batches;
    }

    /**
     * Reorder batches so viewport-visible content translates first.
     *
     * Each batch is scored by the minimum top-Y coordinate of its
     * underlying nodes/elements (or +Infinity for purely off-DOM meta
     * targets). Batches with anything visible (top in [0, viewportHeight])
     * score 0 to surface first.
     */
    sortByVisibility(batches) {
      const viewportH = global.innerHeight || 800;
      const scored = batches.map((batch, index) => {
        let minY = Infinity;
        let anyVisible = false;
        for (const t of batch) {
          const el =
            t.source.kind === "text" ? t.source.node.parentElement : t.source.element;
          if (!el || !el.getBoundingClientRect) continue;
          const r = el.getBoundingClientRect();
          if (r.top < minY) minY = r.top;
          if (r.bottom > 0 && r.top < viewportH) anyVisible = true;
        }
        // Visible items sort to 0 (no further tie-break beyond original
        // index). Items below the fold sort by their distance from the
        // top of the page. Meta targets (Infinity Y) come last.
        const visibilityScore = anyVisible ? 0 : minY;
        return { batch, score: visibilityScore, index };
      });
      scored.sort((a, b) => a.score - b.score || a.index - b.index);
      return scored.map((s) => s.batch);
    }

    // ---- network --------------------------------------------------------

    async translateBatch(batch) {
      // Split cache hits from network items so the server is only asked for
      // misses. The order of items in the returned ``translations`` map is
      // preserved by id, not position.
      const cached = new Map();
      const remote = [];
      for (const t of batch) {
        const hit = this.cache.get(t.text, this.targetLang, this.profileSlug);
        if (hit !== null) {
          cached.set(t.id, { id: t.id, text: hit, cached: true });
        } else {
          remote.push({ id: t.id, text: t.text });
        }
      }

      let remoteResults = [];
      if (remote.length) {
        const start = performance.now();
        const body = {
          target_lang: this.targetLang,
          profile_slug: this.profileSlug,
          items: remote,
        };
        if (this.sourceLang) body.source_lang = this.sourceLang;

        const resp = await fetch(`${this.apiUrl}/translate/batch`, {
          method: "POST",
          headers: this._headers(),
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          const err = await resp.text();
          throw new Error(`Batch request failed: HTTP ${resp.status} ${err}`);
        }
        const json = await resp.json();
        remoteResults = json.translations || [];
        // Populate client cache for everything the server gave us back.
        // We index the original batch by id so we can pair source text
        // with its translation.
        const byId = new Map(batch.map((t) => [t.id, t]));
        for (const r of remoteResults) {
          if (r.error) continue;
          const t = byId.get(r.id);
          if (t) this.cache.set(t.text, this.targetLang, this.profileSlug, r.text);
        }
        const elapsed = performance.now() - start;
        this._log(`batch /translate/batch: ${remote.length} items in ${elapsed.toFixed(0)}ms`, {
          cached_hits: cached.size,
          remote_hits: remoteResults.length,
        });
      } else {
        this._log(`batch served entirely from client cache (${cached.size} items)`);
      }

      const merged = [];
      for (const t of batch) {
        if (cached.has(t.id)) {
          merged.push(cached.get(t.id));
        } else {
          const r = remoteResults.find((x) => x.id === t.id);
          if (r) merged.push(r);
        }
      }
      return merged;
    }

    // ---- application ----------------------------------------------------

    applyTranslations(batch, results) {
      const byId = new Map(batch.map((t) => [t.id, t]));
      for (const r of results) {
        if (r.error) {
          this._log("per-item error, skipped", r);
          continue;
        }
        const t = byId.get(r.id);
        if (!t) continue;

        if (t.source.kind === "text") {
          // Preserve original leading/trailing whitespace so inline layout
          // (e.g. " hello " between two <span>s) doesn't collapse weirdly.
          t.source.node.nodeValue =
            t.source.originalLeading + r.text + t.source.originalTrailing;
          // Mark the *parent element* — text nodes don't carry attributes,
          // so the next collection pass uses the parent's attr to skip.
          if (t.source.node.parentElement) {
            t.source.node.parentElement.setAttribute("data-translated", "1");
          }
        } else if (t.source.kind === "attr") {
          t.source.element.setAttribute(t.source.attr, r.text);
          // Don't tag the element with data-translated here — it might
          // also have body text we still need to translate. The collector
          // skips already-set attributes by checking the value.
        }
      }
    }

    // ---- orchestration --------------------------------------------------

    async translatePage(root) {
      // Fetch profile version once so subsequent caches use the right key.
      if (this.profileVersion === "0") await this._fetchProfileVersion();

      const targets = this.collectTextNodes(root);
      if (!targets.length) {
        this._log("no translatable targets");
        return { translated: 0, cached: 0 };
      }
      this._log(`collected ${targets.length} targets`);

      let batches = this.batchGroups(targets);
      batches = this.sortByVisibility(batches);
      this._log(`${batches.length} batches after viewport sort`);

      let total = 0;
      let cachedCount = 0;
      for (const batch of batches) {
        try {
          const results = await this.translateBatch(batch);
          this.applyTranslations(batch, results);
          total += results.length;
          cachedCount += results.filter((r) => r.cached).length;
        } catch (e) {
          // Don't let a batch failure abort the entire page. Surfacing
          // through console.error gives the operator something to find
          // without breaking the user's experience.
          console.error("[Translator] batch failed", e);
        }
      }
      this._log("translatePage done", { total, cachedCount });
      return { translated: total, cached: cachedCount };
    }

    // ---- mutations ------------------------------------------------------

    observeMutations(root) {
      root = root || document.body;
      if (this._mutationObserver) this._mutationObserver.disconnect();

      this._mutationObserver = new MutationObserver((mutations) => {
        // Cheap filter: only re-translate when at least one mutation added
        // a *text-bearing* node. Pure attribute changes by us (we set
        // ``data-translated``) shouldn't loop us back into translation.
        let interesting = false;
        for (const m of mutations) {
          if (m.type === "childList" && m.addedNodes.length) {
            for (const n of m.addedNodes) {
              if (n.nodeType === Node.TEXT_NODE && n.nodeValue && n.nodeValue.trim()) {
                interesting = true;
                break;
              }
              if (n.nodeType === Node.ELEMENT_NODE) {
                interesting = true;
                break;
              }
            }
          }
          if (interesting) break;
        }
        if (!interesting) return;

        // Debounce so a burst of mutations (SPA route render, list append)
        // becomes one translate pass at most every ``debounceMs``.
        if (this._mutationTimer) clearTimeout(this._mutationTimer);
        this._mutationTimer = setTimeout(() => {
          this._mutationTimer = null;
          this.translatePage(root).catch((e) =>
            console.error("[Translator] mutation translate failed", e)
          );
        }, this.debounceMs);
      });

      this._mutationObserver.observe(root, {
        childList: true,
        subtree: true,
      });
      this._log("MutationObserver attached", root);
    }
  }

  // ---- exports ------------------------------------------------------------

  global.Translator = Translator;
  global.TranslatorClientCache = ClientCache;
})(typeof window !== "undefined" ? window : globalThis);
