// WorkTimer Link — reports the active tab to the local app over loopback.
// All data stays on this device; nothing is sent anywhere else.
const HOST = "http://127.0.0.1:8765";

async function report(tab) {
  if (!tab || !tab.url) return;
  if (!/^https?:/i.test(tab.url)) return;
  try {
    await fetch(HOST + "/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: tab.url,
        title: tab.title || "",
        incognito: !!tab.incognito,
      }),
    });
  } catch (e) {
    // app not running; ignore
  }
}

chrome.tabs.onActivated.addListener(async (info) => {
  const tab = await chrome.tabs.get(info.tabId);
  report(tab);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.title) report(tab);
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  const tabs = await chrome.tabs.query({ active: true, windowId });
  if (tabs[0]) report(tabs[0]);
});
