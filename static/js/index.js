document.getElementById("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = document.getElementById("query").value.trim();
  window.location.href = `/conversation?q=${encodeURIComponent(q)}`;
});

async function loadPast() {
  const listEl = document.getElementById("past-list");
  try {
    const res = await fetch("/conversations");
    const rows = await res.json();
    if (rows.length === 0) {
      listEl.innerHTML = '<li class="muted">No conversations yet.</li>';
      return;
    }
    listEl.innerHTML = "";
    for (const row of rows) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = `/conversation?id=${row.id}`;
      a.textContent = row.query;
      const ts = document.createElement("span");
      ts.className = "ts";
      ts.textContent = new Date(row.created_at).toLocaleString();
      li.appendChild(a);
      li.appendChild(ts);
      listEl.appendChild(li);
    }
  } catch {
    listEl.innerHTML = '<li class="muted">Could not load past conversations.</li>';
  }
}

loadPast();
