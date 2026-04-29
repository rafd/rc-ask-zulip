const params = new URLSearchParams(window.location.search);
const q = params.get("q") || "";
const convId = params.get("id") || "";
document.getElementById("question").textContent = q;
document.title = q ? `${q} — Ask RC Zulip` : "Ask RC Zulip";

const MD_BULLET_LINE = /^\s*[-*+]\s+(.*)$/;

/** Plain-text + markdown-style bullets (-, *, +) → <p> and <ul><li> (safe: text nodes only). */
function appendAnswerTextBlocks(container, text) {
  const lines = String(text).replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i++;
      continue;
    }
    if (MD_BULLET_LINE.test(line)) {
      const ul = document.createElement("ul");
      ul.className = "answer-text-list";
      while (i < lines.length) {
        const m = MD_BULLET_LINE.exec(lines[i]);
        if (!m) break;
        const li = document.createElement("li");
        li.textContent = m[1];
        ul.appendChild(li);
        i++;
      }
      container.appendChild(ul);
      continue;
    }
    const paraLines = [];
    while (i < lines.length) {
      const l = lines[i];
      if (l.trim() === "") break;
      if (MD_BULLET_LINE.test(l)) break;
      paraLines.push(l);
      i++;
    }
    if (paraLines.length) {
      const p = document.createElement("p");
      p.className = "answer-text-para";
      p.textContent = paraLines.join("\n");
      container.appendChild(p);
    }
  }
}

function initSpoilers(container) {
  for (const block of container.querySelectorAll(".spoiler-block")) {
    const header = block.querySelector(".spoiler-header");
    const content = block.querySelector(".spoiler-content");
    if (!header || !content) continue;

    const title = document.createElement("span");
    title.className = "spoiler-title";
    title.textContent = header.textContent.trim() || "Spoiler";
    header.textContent = "";

    const toggle = document.createElement("span");
    toggle.className = "spoiler-toggle";
    toggle.textContent = "▶ show";

    header.appendChild(title);
    header.appendChild(toggle);

    header.addEventListener("click", () => {
      const open = content.classList.toggle("open");
      toggle.textContent = open ? "▼ hide" : "▶ show";
    });
  }
}

function buildSearchedToolMessage(msg) {
  const queries = msg.tool_calls.flatMap(tc => {
    try { return JSON.parse(tc.function.arguments).queries || []; } catch { return []; }
  });
  if (queries.length === 0) return null;

  const div = document.createElement("div");
  div.className = "message tool";

  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = "searched";
  div.appendChild(roleEl);

  const tagLine = document.createElement("div");
  tagLine.className = "search-tags";
  for (const query of queries) {
    const tag = document.createElement("span");
    tag.className = "search-tag";
    tag.textContent = query;
    tagLine.appendChild(tag);
  }
  div.appendChild(tagLine);
  return div;
}

function buildCitationItem(message) {
  const item = document.createElement("div");
  item.className = "cite-item";

  const meta = document.createElement("div");
  meta.className = "cite-meta";
  const ts = message.timestamp ? new Date(message.timestamp * 1000).toLocaleString() : "";
  meta.textContent = `#${message.display_recipient} > ${message.subject}${ts ? " · " + ts : ""}`;

  const body = document.createElement("div");
  body.className = "cite-body";
  body.innerHTML = message.content;
  initSpoilers(body);

  item.appendChild(meta);
  item.appendChild(body);

  const expand = document.createElement("button");
  expand.type = "button";
  expand.className = "cite-expand";
  expand.textContent = "Show more";
  expand.addEventListener("click", () => {
    body.classList.add("is-expanded");
    expand.classList.remove("is-visible");
  });
  item.appendChild(expand);

  requestAnimationFrame(() => {
    if (body.scrollHeight > body.clientHeight) expand.classList.add("is-visible");
  });

  return item;
}

function buildCitationsBlock(messageIds, messageById) {
  const inner = document.createElement("div");
  inner.className = "cite-details-inner";
  for (const id of messageIds) {
    const m = messageById[id];
    if (!m) continue;
    inner.appendChild(buildCitationItem(m));
  }
  if (inner.childElementCount === 0) return null;

  const details = document.createElement("details");
  details.className = "cite-details";
  const summary = document.createElement("summary");
  summary.className = "cite-summary";

  const sumLabel = document.createElement("span");
  sumLabel.className = "cite-summary-text";
  sumLabel.textContent = "See what people are saying";
  summary.appendChild(sumLabel);

  const chevron = document.createElement("span");
  chevron.className = "cite-summary-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = ">";
  summary.appendChild(chevron);

  details.appendChild(summary);
  details.appendChild(inner);
  return details;
}

function buildAnswerMessage(msg, messageById) {
  const div = document.createElement("div");
  div.className = "message assistant final-answer";

  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = "answer";
  div.appendChild(roleEl);

  let sections;
  try {
    const parsed = JSON.parse(msg.content);
    sections = Array.isArray(parsed) ? parsed : parsed?.sections ?? null;
  } catch { sections = null; }

  if (!Array.isArray(sections)) {
    const p = document.createElement("p");
    p.className = "fallback-answer";
    p.textContent = msg.content;
    div.appendChild(p);
    return div;
  }

  for (const section of sections) {
    if ("heading" in section && typeof section.heading === "string" && section.heading.trim()) {
      const h = document.createElement("h3");
      h.className = "answer-section-heading";
      h.textContent = section.heading.trim();
      div.appendChild(h);
    }
    if (section.text) {
      const wrap = document.createElement("div");
      wrap.className = "answer-text";
      appendAnswerTextBlocks(wrap, section.text);
      if (wrap.firstChild) div.appendChild(wrap);
    }
    if (Array.isArray(section.message_ids)) {
      const block = buildCitationsBlock(section.message_ids, messageById);
      if (block) div.appendChild(block);
    }
  }

  return div;
}

function buildMessageById(messages) {
  const messageById = {};
  for (const msg of messages) {
    if (msg.role !== "tool") continue;
    let parsed;
    try { parsed = JSON.parse(msg.content); } catch { parsed = null; }
    if (Array.isArray(parsed)) {
      for (const m of parsed) messageById[m.id] = m;
    }
  }
  return messageById;
}

function renderDebug(messages) {
  const debugEl = document.getElementById("conversation-debug");
  const allMessages = messages.map(m => {
    if (m.role === "tool") {
      let parsed; try { parsed = JSON.parse(m.content); } catch { parsed = m.content; }
      return { ...m, content: parsed };
    }
    return m;
  });
  const pre = document.createElement("pre");
  pre.className = "debug-pre";
  pre.textContent = JSON.stringify(allMessages, null, 2);
  debugEl.appendChild(pre);
}

function render(messages, finalAnswer, convEl) {
  document.getElementById("view-toggle").style.display = "";
  renderDebug(messages);

  const messageById = buildMessageById(messages);

  for (const msg of messages) {
    if (msg.role === "system" || msg.role === "user" || msg.role === "tool") continue;

    let div = null;
    if (msg.role === "assistant" && msg.tool_calls) {
      div = buildSearchedToolMessage(msg);
    } else if (msg.role === "assistant" && msg.content) {
      div = buildAnswerMessage(msg, messageById);
    }
    if (div) convEl.appendChild(div);
  }
}

async function load() {
  const statusEl = document.getElementById("status");
  const errorEl = document.getElementById("error");
  const convEl = document.getElementById("conversation");

  try {
    if (convId) {
      statusEl.textContent = "";
      const res = await fetch(`/conversation-data/${encodeURIComponent(convId)}`);
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const row = await res.json();
      document.getElementById("question").textContent = row.query;
      document.title = `${row.query} — Ask RC Zulip`;
      render(row.messages, row.final_answer, convEl);
      return;
    }
    const res = await fetch(`/ask?q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    statusEl.textContent = "";
    history.replaceState(null, "", `/conversation?id=${data.id}`);
    render(data.messages, data.final_answer, convEl);
  } catch (err) {
    statusEl.textContent = "";
    errorEl.textContent = `Error: ${err.message}`;
  }
}

function setView(v) {
  document.getElementById("conversation").style.display = v === "nice" ? "" : "none";
  document.getElementById("conversation-debug").style.display = v === "debug" ? "" : "none";
  document.getElementById("btn-nice").classList.toggle("active", v === "nice");
  document.getElementById("btn-debug").classList.toggle("active", v === "debug");
}

document.getElementById("btn-nice").addEventListener("click", () => setView("nice"));
document.getElementById("btn-debug").addEventListener("click", () => setView("debug"));

load();
