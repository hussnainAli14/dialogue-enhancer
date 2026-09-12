const DEFAULTS = {
  apiUrl: "http://localhost:8000",
  dashboardUrl: "http://localhost:3000",
};

const statusEl = document.getElementById("status");
const listEl = document.getElementById("list");
const hintEl = document.getElementById("hint");

function setStatus(text, kind) {
  statusEl.textContent = text;
  statusEl.className = kind ? `status ${kind}` : "status";
}

function truncate(text, n) {
  const t = (text || "").trim();
  return t.length > n ? `${t.slice(0, n).trim()}…` : t;
}

function siteFromHost(host) {
  if (host.endsWith("linkedin.com")) return "linkedin";
  if (host.endsWith("reddit.com")) return "reddit";
  return null;
}

async function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(DEFAULTS, resolve);
  });
}

async function ensureApiAccess(apiUrl) {
  let origin;
  try {
    origin = `${new URL(apiUrl).origin}/*`;
  } catch {
    throw new Error("The API URL in Options is not a valid URL.");
  }
  const have = await chrome.permissions.contains({ origins: [origin] });
  if (have) return;
  const granted = await chrome.permissions.request({ origins: [origin] });
  if (!granted) throw new Error("Permission to reach the API was denied.");
}

async function submitPost(apiUrl, dashboardUrl, post) {
  await ensureApiAccess(apiUrl);
  const res = await fetch(`${apiUrl.replace(/\/$/, "")}/conversations/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      platform: post.platform,
      post_url: post.post_url,
      post_author: post.post_author,
      original_post: post.original_post,
      full_thread: post.full_thread,
      source: post.source,
    }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || !body.success) {
    throw new Error(body.error || `Submit failed (${res.status})`);
  }
  const id = body.data?.conversation_id;
  if (id) {
    chrome.tabs.create({
      url: `${dashboardUrl.replace(/\/$/, "")}/conversations/${id}`,
    });
  }
}

function renderPosts(posts, settings) {
  listEl.innerHTML = "";
  hintEl.classList.remove("hidden");
  posts.forEach((post) => {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <div class="author">${escapeHtml(post.post_author || "Unknown author")}</div>
      <div class="excerpt">${escapeHtml(truncate(post.original_post, 280))}</div>
    `;
    const btn = document.createElement("button");
    btn.textContent = posts.length > 1 ? "Send this post" : "Send to Dialogue Enhancer";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      setStatus("Sending…");
      try {
        await submitPost(settings.apiUrl, settings.dashboardUrl, post);
        setStatus("Sent. Opening the dashboard…", "ok");
      } catch (err) {
        btn.disabled = false;
        setStatus(err instanceof Error ? err.message : "Submit failed", "error");
      }
    });
    card.appendChild(btn);
    listEl.appendChild(card);
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function main() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) {
    setStatus("No active tab.", "error");
    return;
  }

  let host = "";
  try {
    host = new URL(tab.url).hostname;
  } catch {
    setStatus("This tab has no page URL.", "error");
    return;
  }

  const site = siteFromHost(host);
  if (!site) {
    setStatus("Open a LinkedIn or Reddit post, then click this icon again.", "error");
    return;
  }

  const settings = await loadSettings();

  let injected;
  try {
    injected = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: extractPagePosts,
    });
  } catch {
    try {
      injected = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: extractPagePosts,
      });
    } catch (err) {
      setStatus(
        err instanceof Error ? err.message : "Could not read this page.",
        "error"
      );
      return;
    }
  }

  const posts = [];
  const seen = new Set();
  let lastDebug = null;
  let lastError = null;
  for (const frame of injected || []) {
    if (frame.error) lastError = String(frame.error);
    const result = frame.result;
    if (result?.error) lastError = result.error;
    if (result?.debug) lastDebug = result.debug;
    for (const post of result?.posts || []) {
      const key = (post.original_post || "").slice(0, 80);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      posts.push(post);
    }
  }

  if (!posts.length) {
    const extra = lastError ? ` (${lastError})` : "";
    const body = lastDebug?.body ?? 0;
    const label = site === "reddit" ? "Reddit" : "LinkedIn";
    setStatus(
      body
        ? `Could not isolate the post text${extra}. Open the post itself, then try again.`
        : `This tab has no readable post text${extra}. Reload the ${label} tab, then click the clipper again.`,
      "error"
    );
    return;
  }

  setStatus(
    posts.length === 1
      ? "This is the post on the page. Send it when you are ready."
      : `${posts.length} posts are visible. Pick the one you are reading.`
  );
  renderPosts(posts, settings);
}

main();
