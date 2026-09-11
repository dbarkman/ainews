/* AI News HQ — survey, digest, sources. No framework, no build step. */
"use strict";

const KEY = "ainewshq.profile.v1";

/* Survey answers map to topic slugs. Kept as plain data so the mapping is
   auditable and easy to tune without touching any logic. */
const QUESTIONS = {
  industry: [
    ["software",   "Software / tech",     ["coding", "agents"]],
    ["healthcare", "Healthcare",          ["applied", "policy"]],
    ["finance",    "Finance",             ["applied", "business"]],
    ["marketing",  "Marketing / sales",   ["applied", "business"]],
    ["energy",     "Energy / utilities",  ["power", "chips"]],
    ["manufact",   "Manufacturing",       ["robotics", "applied"]],
    ["education",  "Education",           ["applied", "policy"]],
    ["other",      "Something else",      []],
  ],
  today: [
    ["writing",  "Writing and summarising", ["llms"]],
    ["code",     "Writing code",            ["coding"]],
    ["research", "Research and analysis",   ["llms", "applied"]],
    ["automate", "Automating workflows",    ["agents"]],
    ["none",     "Not much yet",            []],
  ],
  next: [
    ["build",    "Build AI into a product",   ["agents", "coding"]],
    ["team",     "Roll it out to a team",     ["policy", "applied"]],
    ["evaluate", "Decide what to buy/build",  ["business", "llms"]],
    ["govern",   "Govern it responsibly",     ["policy", "safety"]],
  ],
  learn: [
    ["models",   "Model releases",        ["llms"]],
    ["agents",   "Agents and tooling",    ["agents"]],
    ["dev",      "Coding with AI",        ["coding"]],
    ["infra",    "Chips and datacenters", ["chips"]],
    ["power",    "Power and energy use",  ["power"]],
    ["robots",   "Robotics",              ["robotics"]],
    ["safety",   "Safety and alignment",  ["safety"]],
    ["policy",   "Policy and regulation", ["policy"]],
    ["money",    "Funding and business",  ["business"]],
    ["applied",  "Industry applications", ["applied"]],
  ],
  limit: [["3", "3 — just the signal", []], ["7", "7 — a short read", []], ["15", "15 — I read a lot", []]],
};

/* Question 4 is the explicit answer, so it counts for more than the inferred ones. */
const Q_WEIGHT = { learn: 3, next: 2, today: 1, industry: 1 };

let profile = null;
let topicsMeta = [];

const $ = (sel) => document.querySelector(sel);
const setStatus = (msg) => { $("#status").textContent = msg || ""; };

function loadProfile() {
  try { return JSON.parse(localStorage.getItem(KEY) || "null"); }
  catch { return null; }
}
function saveProfile(p) {
  try { localStorage.setItem(KEY, JSON.stringify(p)); }
  catch { setStatus("Couldn't save settings — private browsing?"); }
}

function scoreTopics(answers) {
  const scores = {};
  for (const [q, picks] of Object.entries(answers)) {
    if (q === "limit") continue;
    const defs = QUESTIONS[q] || [];
    for (const pick of [].concat(picks)) {
      const def = defs.find((d) => d[0] === pick);
      if (!def) continue;
      for (const slug of def[2]) scores[slug] = (scores[slug] || 0) + (Q_WEIGHT[q] || 1);
    }
  }
  return Object.entries(scores).sort((a, b) => b[1] - a[1]).map(([slug]) => slug);
}

/* ---------------------------------------------------------------- rendering */

function chip(value, label, pressed) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "opt";
  b.dataset.value = value;
  b.textContent = label;
  b.setAttribute("aria-pressed", pressed ? "true" : "false");
  b.addEventListener("click", () => {
    const single = b.parentElement.dataset.single === "1";
    if (single) {
      [...b.parentElement.children].forEach((c) => c.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
    } else {
      b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") === "true" ? "false" : "true");
    }
  });
  return b;
}

function picked(container) {
  return [...container.querySelectorAll('.opt[aria-pressed="true"]')].map((b) => b.dataset.value);
}

function buildSurvey() {
  document.querySelectorAll("#survey-form .options").forEach((box) => {
    const defs = QUESTIONS[box.dataset.q] || [];
    box.replaceChildren(...defs.map((d) => chip(d[0], d[1], d[0] === "7")));
  });
}

function timeAgo(iso) {
  const mins = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function renderFeed(data) {
  const list = $("#feed-list");
  list.replaceChildren(...data.items.map((it) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = it.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer external";
    a.textContent = it.title;
    const meta = document.createElement("div");
    meta.className = "meta";
    for (const t of [it.source.name, it.topic.name, timeAgo(it.published_at), it.why]) {
      const s = document.createElement("span");
      s.className = "badge";
      s.textContent = t;
      meta.appendChild(s);
    }
    li.append(a, meta);
    return li;
  }));
  $("#feed-empty").hidden = data.items.length > 0;
  $("#feed-meta").textContent =
    `${data.count} of up to ${data.limit} · ${data.topics.length || "all"} topics`;
}

function renderSources(data) {
  const byKind = { topical: [], broad: [] };
  data.sources.forEach((s) => byKind[s.kind]?.push(s));
  const box = $("#sources-list");
  box.replaceChildren();
  for (const [kind, heading, blurb] of [
    ["topical", "Dedicated to your topics", "Everything they publish is on-beat."],
    ["broad", "General AI sources", "Filtered per article to your topics."],
  ]) {
    if (!byKind[kind].length) continue;
    const h = document.createElement("h3");
    h.textContent = heading;
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = blurb;
    box.append(h, p);
    byKind[kind].forEach((s) => {
      const d = document.createElement("div");
      d.className = "src";
      const t = document.createElement("h4");
      const a = document.createElement("a");
      a.href = s.homepage_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer external";
      a.textContent = s.name;
      t.appendChild(a);
      const b = document.createElement("p");
      b.className = "hint";
      b.textContent = s.blurb;
      d.append(t, b);
      box.appendChild(d);
    });
  }
}

function buildSettings() {
  const topicBox = $("#settings-topics");
  topicBox.replaceChildren(...topicsMeta.map((t) =>
    chip(t.slug, t.name, profile.topics.includes(t.slug))));
  const limitBox = $("#settings-limit");
  limitBox.dataset.single = "1";
  limitBox.replaceChildren(...QUESTIONS.limit.map((d) =>
    chip(d[0], d[1], String(profile.limit) === d[0])));
}

/* ------------------------------------------------------------------- views */

async function show(view) {
  ["survey", "feed", "sources", "settings"].forEach((v) => { $("#" + v).hidden = v !== view; });
  document.querySelectorAll("#nav button").forEach((b) =>
    b.setAttribute("aria-current", b.dataset.view === view ? "true" : "false"));
  $("#nav").hidden = !profile;

  try {
    if (view === "feed") {
      setStatus("Loading…");
      const q = new URLSearchParams({ topics: profile.topics.join(","), limit: profile.limit });
      renderFeed(await (await fetch("/api/feed?" + q)).json());
      setStatus("");
    } else if (view === "sources") {
      setStatus("Loading…");
      const q = new URLSearchParams({ topics: profile.topics.join(",") });
      renderSources(await (await fetch("/api/sources?" + q)).json());
      setStatus("");
    } else if (view === "settings") {
      buildSettings();
    }
  } catch (err) {
    setStatus("Couldn't reach the server.");
  }
}

async function init() {
  try {
    topicsMeta = (await (await fetch("/api/topics")).json()).topics;
  } catch {
    setStatus("Couldn't load topics.");
    return;
  }

  profile = loadProfile();
  buildSurvey();

  $("#survey-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const answers = {};
    document.querySelectorAll("#survey-form .options").forEach((box) => {
      answers[box.dataset.q] = picked(box);
    });
    const topics = scoreTopics(answers);
    profile = {
      answers,
      topics: topics.length ? topics : topicsMeta.map((t) => t.slug),
      limit: Number(answers.limit?.[0] || 7),
    };
    saveProfile(profile);
    show("feed");
  });

  $("#save-settings").addEventListener("click", () => {
    profile.topics = picked($("#settings-topics"));
    profile.limit = Number(picked($("#settings-limit"))[0] || 7);
    if (!profile.topics.length) profile.topics = topicsMeta.map((t) => t.slug);
    saveProfile(profile);
    show("feed");
  });

  $("#retake").addEventListener("click", () => { profile = null; buildSurvey(); show("survey"); });
  document.querySelectorAll("#nav button").forEach((b) =>
    b.addEventListener("click", () => show(b.dataset.view)));

  show(profile ? "feed" : "survey");
}

init();
