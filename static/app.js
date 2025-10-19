function $(id) { return document.getElementById(id); }

function setHealth(status, time) {
  const el = $("health");
  if (!el) return;
  if (status === "ok") {
    el.textContent = `Backend OK (${new Date(time * 1000).toLocaleTimeString()})`;
    el.classList.remove("bad");
    el.classList.add("good");
  } else {
    el.textContent = `Backend unreachable`;
    el.classList.remove("good");
    el.classList.add("bad");
  }
}

async function checkHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    setHealth(data.status, data.time);
  } catch (e) {
    setHealth("bad");
  }
}

function showError(msg) {
  $("errorSection").classList.remove("hidden");
  $("errorMsg").textContent = msg || "Unknown error";
}

function hideError() {
  $("errorSection").classList.add("hidden");
  $("errorMsg").textContent = "";
}

function showResult(payload) {
  const sec = $("resultSection");
  sec.classList.remove("hidden");

  const result = (payload.result || '').toString();
  const id = payload.id || payload._id || '—';
  const meta = payload.meta || {};

  $("decision").textContent = result;
  $("docId").textContent = id;
  $("afterHours").textContent = String(payload.after_hours ?? meta.after_hours ?? false);
  $("origin").textContent = meta.origin || '—';
  $("raw").textContent = JSON.stringify(payload, null, 2);

  const badge = $("resultBadge");
  badge.textContent = result || '—';
  badge.classList.remove("fraud", "notfraud", "mediate");
  const lower = result.toLowerCase();
  if (lower.includes('fraud') && !lower.includes('not')) {
    badge.classList.add("fraud");
  } else if (lower.includes('not')) {
    badge.classList.add("notfraud");
  } else {
    badge.classList.add("mediate");
  }
}

function setLoading(isLoading) {
  $("loading").classList.toggle("hidden", !isLoading);
}

async function submitMessage(e) {
  e.preventDefault();
  hideError();
  $("resultSection").classList.add("hidden");

  const message = $("message").value.trim();
  if (!message) {
    showError("Please enter a message");
    return;
  }

  setLoading(true);
  try {
    const res = await fetch('/api/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'website', message })
    });
    if (!res.ok) {
      let msg = `Server error (${res.status})`;
      try {
        const err = await res.json();
        if (err && err.error) msg = err.error;
      } catch {}
      throw new Error(msg);
    }
    const payload = await res.json();
    showResult(payload);
  } catch (err) {
    console.error(err);
    showError(err.message || String(err));
  } finally {
    setLoading(false);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  setInterval(checkHealth, 15000);
  const form = $("msgForm");
  form.addEventListener('submit', submitMessage);
});
