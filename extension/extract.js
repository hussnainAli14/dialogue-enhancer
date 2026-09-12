/**
 * Reads the post already on the current LinkedIn or Reddit page.
 * Does not scroll, click, search, or navigate.
 *
 * Helpers live inside this function so chrome.scripting.executeScript can
 * serialize the whole thing into the tab.
 */
function extractPagePosts() {
  try {
    const host = location.hostname;
    if (host.endsWith("reddit.com")) return runRedditExtract();
    if (host.endsWith("linkedin.com")) return runLinkedInExtract();
    return { posts: [], error: "unsupported-site", debug: {} };
  } catch (err) {
    return {
      posts: [],
      error: err instanceof Error ? err.message : String(err),
      debug: { body: (document.body?.innerText || "").length },
    };
  }

  function visibleText(el) {
    if (!el) return "";
    return (el.innerText || el.textContent || "")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function shadowOf(el) {
    if (!el) return null;
    if (el.shadowRoot) return el.shadowRoot;
    try {
      if (typeof chrome !== "undefined" && chrome.dom?.openOrClosedShadowRoot) {
        return chrome.dom.openOrClosedShadowRoot(el);
      }
    } catch {
      /* ignore */
    }
    return null;
  }

  function queryAllDeep(root, selector) {
    const out = [];
    const visit = (node) => {
      if (!node?.querySelectorAll) return;
      try {
        node.querySelectorAll(selector).forEach((el) => out.push(el));
      } catch {
        /* ignore */
      }
      let els = [];
      try {
        els = node.querySelectorAll("*");
      } catch {
        return;
      }
      for (const el of els) {
        const shadow = shadowOf(el);
        if (shadow) visit(shadow);
      }
    };
    visit(root);
    return out;
  }

  function deepText(root) {
    if (!root) return "";
    const parts = [root.innerText || ""];
    let els = [];
    try {
      els = root.querySelectorAll("*");
    } catch {
      return parts.join("\n").trim();
    }
    for (const el of els) {
      const shadow = shadowOf(el);
      if (shadow) parts.push(deepText(shadow));
    }
    return parts.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function outermost(nodes) {
    const arr = [...new Set(nodes)].filter(Boolean);
    return arr.filter((el) => !arr.some((other) => other !== el && other.contains?.(el)));
  }

  function pickLongest(root, selectors, skip) {
    let best = "";
    if (!root) return best;
    for (const sel of selectors) {
      const nodes = queryAllDeep(root, sel);
      for (const node of nodes) {
        if (skip && skip(node)) continue;
        const t = visibleText(node);
        if (t.length > best.length) best = t;
      }
    }
    return best;
  }

  function fallbackPagePost(platform, source) {
    const main = document.querySelector("main") || document.body;
    const raw = deepText(main) || visibleText(main) || deepText(document.body);
    if (raw.length < 40) return null;
    return {
      platform,
      source,
      post_url: location.href.split(/[?#]/)[0],
      post_author: null,
      original_post: raw.slice(0, 4000),
      full_thread: raw.slice(0, 8000),
    };
  }

  function runRedditExtract() {
    function inComment(el) {
      try {
        const tag = (el.tagName || "").toLowerCase();
        if (tag === "shreddit-comment") return true;
        return !!(el.closest && el.closest("shreddit-comment, div.comment, .commentarea"));
      } catch {
        return false;
      }
    }

    function collectContainers() {
      const found = [];
      queryAllDeep(document, "shreddit-post").forEach((el) => found.push(el));
      queryAllDeep(document, '[data-testid="post-container"]').forEach((el) => found.push(el));
      queryAllDeep(document, "div.thing.link, div.link.thing").forEach((el) => found.push(el));
      return outermost(found);
    }

    function authorOf(el) {
      return (
        el.getAttribute?.("author") ||
        pickLongest(el, ['a[href*="/user/"]', 'a[href*="/u/"]', "a.author", '[slot="authorName"]'])
          .split("\n")[0]
          .replace(/^u\//, "")
          .trim() ||
        null
      );
    }

    function titleOf(el) {
      return (
        el.getAttribute?.("post-title") ||
        pickLongest(el, [
          '[slot="title"]',
          '[id^="post-title"]',
          "h1",
          "a.title",
          '[data-adclicklocation="title"]',
        ])
      );
    }

    function bodyOf(el) {
      return pickLongest(
        el,
        [
          '[slot="text-body"]',
          '[id*="post-rtjson"]',
          "div.md",
          ".usertext-body",
          '[data-click-id="text"]',
        ],
        inComment
      );
    }

    function urlOf(el) {
      const permalink = el.getAttribute?.("permalink");
      if (permalink) {
        try {
          return new URL(permalink, location.origin).href.split(/[?#]/)[0];
        } catch {
          /* ignore */
        }
      }
      const link = el.querySelector?.(
        'a[data-click-id="body"], a.title, a[href*="/comments/"]'
      );
      if (link?.href && /\/comments\//.test(link.href)) {
        return link.href.split(/[?#]/)[0];
      }
      return location.href.split(/[?#]/)[0];
    }

    function commentsOnPage() {
      const lines = [];
      queryAllDeep(document, "shreddit-comment").forEach((c) => {
        const author = c.getAttribute("author") || "Someone";
        const body = pickLongest(c, ['[slot="comment"]', '[id*="comment-rtjson"]', "div.md"]);
        if (body) lines.push(`${author}: ${body}`);
      });
      queryAllDeep(document, "div.comment").forEach((c) => {
        const author = (
          c.getAttribute("data-author") ||
          visibleText(c.querySelector("a.author")) ||
          "Someone"
        ).split("\n")[0];
        const body = visibleText(c.querySelector(".usertext-body, div.md"));
        if (body) lines.push(`${author}: ${body}`);
      });
      return lines.slice(0, 30);
    }

    const permalink = /\/comments\//.test(location.pathname);
    const all = collectContainers();
    const posts = [];
    const seen = new Set();
    const pageComments = permalink ? commentsOnPage() : [];

    for (const root of all) {
      const title = titleOf(root);
      const body = bodyOf(root);
      const original_post = [title, body].filter(Boolean).join("\n\n");
      if (original_post.length < 8) continue;
      const key = original_post.slice(0, 80);
      if (seen.has(key)) continue;
      seen.add(key);
      const author = authorOf(root);
      posts.push({
        platform: "reddit",
        source: "reddit_clipper",
        post_url: urlOf(root),
        post_author: author,
        original_post,
        full_thread: pageComments.length
          ? `${author || "OP"}: ${original_post}\n\n${pageComments.join("\n\n")}`
          : original_post,
      });
      if (posts.length >= 8) break;
    }

    if (!posts.length) {
      const fallback = fallbackPagePost("reddit", "reddit_clipper");
      if (fallback) posts.push(fallback);
    }

    return {
      platform: "reddit",
      pageUrl: location.href.split(/[?#]/)[0],
      permalink,
      posts,
      debug: {
        containers: all.length,
        body: (document.body?.innerText || "").length,
        main: (document.querySelector("main")?.innerText || "").length,
      },
    };
  }

  function runLinkedInExtract() {
    function inComments(el) {
      try {
        return !!(
          el.closest &&
          el.closest('[class*="comments-comment"], [class*="comments-comments-list"]')
        );
      } catch {
        return false;
      }
    }

    function collectContainers() {
      const sels = [
        '[data-urn*="activity"]',
        '[data-urn*="ugcPost"]',
        '[data-view-name*="feed"]',
        '[data-view-name*="update"]',
        ".feed-shared-update-v2",
        ".occludable-update",
        ".fie-impression-container",
        "article",
        ".artdeco-card",
      ];
      const found = [];
      for (const sel of sels) {
        queryAllDeep(document, sel).forEach((el) => found.push(el));
      }
      queryAllDeep(document, "span.break-words, p, span[dir='ltr']").forEach((node) => {
        if (inComments(node) || visibleText(node).length < 40) return;
        const card =
          node.closest?.(
            '[data-urn], [data-view-name], article, .artdeco-card, [class*="feed-shared"], [class*="fie-impression"]'
          ) || node.parentElement;
        if (card) found.push(card);
      });
      return outermost(found);
    }

    function postText(root) {
      const structured = pickLongest(
        root,
        [
          '[class*="commentary"]',
          '[class*="update-components-text"]',
          '[class*="feed-shared-update"]',
          '[class*="feed-shared-text"]',
          "span.break-words",
          "span[dir='ltr']",
          "p",
        ],
        inComments
      );
      if (structured.length >= 8) return structured;
      const leftover = visibleText(root);
      return leftover.length >= 20 ? leftover.slice(0, 8000) : "";
    }

    function authorName(root) {
      const t = pickLongest(root, [
        '[class*="actor__name"]',
        '[class*="actor__title"]',
        'a[href*="/in/"] span[aria-hidden="true"]',
        'a[href*="/in/"]',
      ]);
      if (!t) return null;
      return t.split("\n")[0].replace(/[·•].*$/, "").trim() || null;
    }

    function postUrl(root) {
      const urn =
        root.getAttribute?.("data-urn") ||
        root.querySelector?.("[data-urn]")?.getAttribute("data-urn");
      if (urn && /activity|ugcPost/.test(urn)) {
        return `https://www.linkedin.com/feed/update/${urn}`;
      }
      const link = root.querySelector?.(
        'a[href*="/posts/"], a[href*="/feed/update/"], a[href*="/pulse/"]'
      );
      if (link?.href) {
        try {
          const u = new URL(link.href, location.origin);
          return `${u.origin}${u.pathname}`;
        } catch {
          /* ignore */
        }
      }
      return location.href.split(/[?#]/)[0];
    }

    function comments(root) {
      const lines = [];
      queryAllDeep(
        root,
        '[class*="comments-comment-entity"], [class*="comments-comment-item"]'
      ).forEach((item) => {
        const author =
          pickLongest(item, ['[class*="comments-post-meta__name"]', 'a[href*="/in/"]']) ||
          "Someone";
        const body = pickLongest(item, [
          '[class*="main-content"]',
          "span.break-words",
          "span[dir='ltr']",
        ]);
        if (body) lines.push(`${author.split("\n")[0]}: ${body}`);
      });
      return lines;
    }

    const permalink = /\/(posts|feed\/update|pulse)\//.test(location.pathname);
    const all = collectContainers();
    const posts = [];
    const seen = new Set();

    for (const root of all) {
      const original_post = postText(root);
      if (original_post.length < 8) continue;
      const key = original_post.slice(0, 80);
      if (seen.has(key)) continue;
      seen.add(key);
      const author = authorName(root);
      const commentLines = comments(root);
      posts.push({
        platform: "linkedin",
        source: "linkedin_clipper",
        post_url: postUrl(root),
        post_author: author,
        original_post,
        full_thread: commentLines.length
          ? `${author || "OP"}: ${original_post}\n\n${commentLines.join("\n\n")}`
          : original_post,
      });
      if (posts.length >= 8) break;
    }

    if (!posts.length) {
      const fallback = fallbackPagePost("linkedin", "linkedin_clipper");
      if (fallback) posts.push(fallback);
    }

    return {
      platform: "linkedin",
      pageUrl: location.href.split(/[?#]/)[0],
      permalink,
      posts,
      debug: {
        containers: all.length,
        body: (document.body?.innerText || "").length,
        main: (document.querySelector("main")?.innerText || "").length,
      },
    };
  }
}

function extractLinkedInPosts() {
  return extractPagePosts();
}
