const PRESETS = {
  local: {
    apiUrl: "http://localhost:8000",
    dashboardUrl: "http://localhost:3000",
  },
  production: {
    apiUrl: "https://dialogue-enhancer.onrender.com",
    dashboardUrl: "https://dialogue-enhancer.vercel.app",
  },
};

const presetEl = document.getElementById("preset");
const apiEl = document.getElementById("apiUrl");
const dashEl = document.getElementById("dashboardUrl");
const statusEl = document.getElementById("status");

function matchPreset(apiUrl, dashboardUrl) {
  for (const [key, value] of Object.entries(PRESETS)) {
    if (value.apiUrl === apiUrl && value.dashboardUrl === dashboardUrl) return key;
  }
  return "custom";
}

chrome.storage.sync.get(
  { apiUrl: PRESETS.local.apiUrl, dashboardUrl: PRESETS.local.dashboardUrl },
  (stored) => {
    apiEl.value = stored.apiUrl;
    dashEl.value = stored.dashboardUrl;
    presetEl.value = matchPreset(stored.apiUrl, stored.dashboardUrl);
  }
);

presetEl.addEventListener("change", () => {
  const preset = PRESETS[presetEl.value];
  if (!preset) return;
  apiEl.value = preset.apiUrl;
  dashEl.value = preset.dashboardUrl;
});

[apiEl, dashEl].forEach((el) => {
  el.addEventListener("input", () => {
    presetEl.value = matchPreset(apiEl.value.trim(), dashEl.value.trim());
  });
});

document.getElementById("save").addEventListener("click", async () => {
  const apiUrl = apiEl.value.trim().replace(/\/$/, "");
  const dashboardUrl = dashEl.value.trim().replace(/\/$/, "");
  try {
    const origin = `${new URL(apiUrl).origin}/*`;
    const have = await chrome.permissions.contains({ origins: [origin] });
    if (!have) {
      const granted = await chrome.permissions.request({ origins: [origin] });
      if (!granted) {
        statusEl.textContent = "Save cancelled — the API host was not allowed.";
        statusEl.className = "status error";
        return;
      }
    }
  } catch {
    statusEl.textContent = "Enter a valid API URL.";
    statusEl.className = "status error";
    return;
  }

  chrome.storage.sync.set({ apiUrl, dashboardUrl }, () => {
    statusEl.textContent = "Saved.";
    statusEl.className = "status ok";
  });
});
