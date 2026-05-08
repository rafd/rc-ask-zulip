/** Matches checkin_topics.BUCKETS iteration order (Other is always last). */
const BUCKET_ORDER = [
  "AI", "Music", "Games", "Rust", "Go", "Zig", "C", "Web", "Python", "Systems",
  "Math", "DevOps", "Data", "Security", "Mobile", "Cloud", "Hardware",
  "Talks/Demos", "Pairing", "Career", "Languages", "Art", "Cooking", "Life",
];

const BUCKET_EMOJI = {
  AI: "🤖",
  Music: "🎵",
  Games: "🎮",
  Rust: "🦀",
  Go: "🐹",
  Zig: "⚡",
  C: "🔧",
  Web: "🌐",
  Python: "🐍",
  Systems: "⚙️",
  Math: "📐",
  DevOps: "🛠️",
  Data: "📊",
  Security: "🔒",
  Mobile: "📱",
  Cloud: "☁️",
  Hardware: "🔌",
  "Talks/Demos": "🎤",
  Pairing: "🧑‍💻",
  Career: "💼",
  Languages: "🗣️",
  Art: "🎨",
  Cooking: "🍳",
  Life: "🌿",
  Other: "✨",
};

function bucketSortKeys(keys) {
  const idx = (k) => {
    if (k === "Other") return 1_000;
    const i = BUCKET_ORDER.indexOf(k);
    return i === -1 ? BUCKET_ORDER.length : i;
  };
  return [...keys].sort((a, b) => {
    const da = idx(a), db = idx(b);
    if (da !== db) return da - db;
    return a.localeCompare(b);
  });
}

async function load() {
  const statusEl = document.getElementById("status");
  const bucketsEl = document.getElementById("buckets");
  try {
    const res = await fetch("/api/checkin-pair");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    statusEl.textContent = "";

    const keys = bucketSortKeys(
      Object.keys(data).filter((k) => data[k] && data[k].length > 0)
    );

    for (const bucket of keys) {
      const people = data[bucket];

      const section = document.createElement("div");
      const h2 = document.createElement("h2");
      const emojiSpan = document.createElement("span");
      emojiSpan.className = "emoji";
      emojiSpan.textContent = BUCKET_EMOJI[bucket] || "📌";
      h2.appendChild(emojiSpan);
      h2.appendChild(document.createTextNode(` ${bucket} `));
      const count = document.createElement("span");
      count.className = "count";
      count.textContent = `(${people.length})`;
      h2.appendChild(count);
      section.appendChild(h2);

      const grid = document.createElement("div");
      grid.className = "grid";

      for (const p of people) {
        grid.appendChild(makeCard(p));
      }

      section.appendChild(grid);
      bucketsEl.appendChild(section);
    }

    if (bucketsEl.children.length === 0) {
      statusEl.textContent = "No check-ins found.";
    }
  } catch (err) {
    statusEl.textContent = `Could not load check-ins: ${err.message}`;
  }
}

function makeCard(p) {
  const card = document.createElement("div");
  card.className = "card";

  if (p.avatar_url) {
    const img = document.createElement("img");
    img.className = "avatar";
    img.src = p.avatar_url;
    img.alt = "";
    img.width = 52;
    img.height = 52;
    img.referrerPolicy = "no-referrer";
    img.addEventListener("error", () => {
      img.replaceWith(avatarFallbackEl(p.name));
    });
    card.appendChild(img);
  } else {
    card.appendChild(avatarFallbackEl(p.name));
  }

  const body = document.createElement("div");
  body.className = "card-body";

  const name = document.createElement("div");
  name.className = "card-name";
  name.textContent = p.name;
  body.appendChild(name);

  if (p.topic_subject) {
    const topic = document.createElement("div");
    topic.className = "card-topic";
    topic.textContent = `Topic: ${p.topic_subject}`;
    body.appendChild(topic);
  }

  if (p.preview) {
    const preview = document.createElement("div");
    preview.className = "card-preview";
    preview.textContent = p.preview;
    body.appendChild(preview);
  }

  const actions = document.createElement("div");
  actions.className = "card-actions";

  if (p.checkin_url) {
    const checkinLink = document.createElement("a");
    checkinLink.className = "btn btn-checkin";
    checkinLink.href = p.checkin_url;
    checkinLink.target = "_blank";
    checkinLink.rel = "noopener noreferrer";
    checkinLink.textContent = "📋 Open check-in";
    actions.appendChild(checkinLink);
  }

  const dmLink = document.createElement("a");
  dmLink.className = "btn btn-dm";
  dmLink.href = p.dm_url;
  dmLink.target = "_blank";
  dmLink.rel = "noopener noreferrer";
  dmLink.textContent = "💬 Open DM";
  actions.appendChild(dmLink);

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "btn btn-copy";
  copyBtn.textContent = "📎 Copy opener";

  const copiedLabel = document.createElement("span");
  copiedLabel.className = "copied-label";
  copiedLabel.textContent = "Copied!";

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(p.suggested_message);
      copiedLabel.classList.add("is-visible");
      setTimeout(() => { copiedLabel.classList.remove("is-visible"); }, 2000);
    } catch {
      prompt("Copy this message:", p.suggested_message);
    }
  });

  actions.appendChild(copyBtn);
  actions.appendChild(copiedLabel);
  body.appendChild(actions);

  card.appendChild(body);
  return card;
}

function avatarFallbackEl(name) {
  const initial = (name && name.trim()[0]) ? name.trim()[0].toUpperCase() : "?";
  const div = document.createElement("div");
  div.className = "avatar avatar-fallback";
  div.setAttribute("aria-hidden", "true");
  div.textContent = initial;
  return div;
}

load();
