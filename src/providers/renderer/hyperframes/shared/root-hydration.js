/*
  Root-level hydration and animation for HyperFrames compositions.

  This file is inlined into the generated root index.html by render_index_html().
  Data injection: Python replaces __HF_DATA_BLOCK__ with const declarations for
  __hfSubtitleCues, __hfStoryMarkers, __hfWaveform, __hfSceneRuntime, __hfTotalDuration.
*/

window.__timelines = window.__timelines || {};

/* ── data block (injected by Python) ── */
__HF_DATA_BLOCK__

/* ── DOM refs ── */
const rootEl = document.querySelector('[data-composition-id="hn-techpulse-root"]');
const subtitleEl = rootEl.querySelector('.hf-subtitle');
const progressBar = rootEl.querySelector('.hf-progress__bar');
const progressTrack = rootEl.querySelector('.hf-progress');
const waveEl = rootEl.querySelector('.hf-waveform');
const waveBars = Array.from({ length: 28 }, () => {
  const s = document.createElement('span');
  waveEl.appendChild(s);
  return s;
});

/* ── utilities ── */
const parseJson = (value, fallback) => {
  try { return JSON.parse(value || ''); } catch (e) { return fallback; }
};
const setText = (root, selector, value) => {
  const el = root.querySelector(selector);
  if (el) el.textContent = value || '';
};
const setHidden = (el, hidden) => {
  if (el) el.style.display = hidden ? 'none' : '';
};
const fillList = (root, selector, items, render) => {
  const el = root.querySelector(selector);
  if (!el) return;
  el.innerHTML = '';
  (items || []).filter(Boolean).forEach((item, index) => {
    const child = render(item, index);
    if (child) el.appendChild(child);
  });
};
const div = (className, text) => {
  const el = document.createElement('div');
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text || '';
  return el;
};

/* ── card hydration ── */
function hydrateCover(host, vars) {
  const root = host.querySelector('.hf-comp-cover');
  if (!root) return false;
  setText(root, '.brand-strip__date', vars.date_label || '');
  setText(root, '.card-title', vars.headline || 'HN 每日观察');
  setText(root, '.card-deck', vars.subtitle || '快讯 / 洞察 / 趋势');
  const lineup = parseJson(vars.lineup_json, []);
  fillList(root, '.opening__list', lineup, (item, index) => {
    const row = div('opening__item');
    row.appendChild(div('opening__index', String(index + 1).padStart(2, '0')));
    row.appendChild(div('opening__text', typeof item === 'string' ? item : (item.title || item.text || item.headline || '')));
    return row;
  });
  return true;
}

function hydrateEvent(host, vars) {
  const root = host.querySelector('.hf-comp-event');
  if (!root) return false;
  setText(root, '.brand-strip__date', vars.date_label || '');
  setText(root, '.card-title', vars.title || '');
  setText(root, '.event-source-title', vars.sub_title || '');
  setText(root, '.lead__src', vars.source_domain || '');
  setText(root, '.metrics', `${Number(vars.score || 0)} points / ${Number(vars.comment_count || 0)} comments`);
  const why = root.querySelector('.why-section');
  const impact = root.querySelector('.impact-section');
  setText(root, '.why-section .section-content', vars.why_it_matters || '');
  setText(root, '.impact-section .section-content', vars.impact || '');
  setHidden(why, !vars.why_it_matters);
  setHidden(impact, !vars.impact);
  const tags = parseJson(vars.tags_json, []);
  fillList(root, '.tags', tags, (tag) => {
    const el = document.createElement('span');
    el.textContent = typeof tag === 'string' ? tag : String(tag || '');
    return el;
  });
  const imageBox = root.querySelector('.event-image');
  if (imageBox && vars.image_src) {
    let img = imageBox.querySelector('img');
    if (!img) { img = document.createElement('img'); imageBox.appendChild(img); }
    img.src = vars.image_src;
    img.alt = vars.title || '';
    setHidden(imageBox, false);
  } else {
    setHidden(imageBox, true);
  }
  return true;
}

function hydrateAtmosphere(host, vars) {
  const root = host.querySelector('.hf-comp-atmosphere');
  if (!root) return false;
  setText(root, '.brand-strip__date', vars.date_label || '');
  setText(root, '.card-title', vars.title || '');
  setText(root, '.card-deck', vars.subtitle || '');
  const stance = parseJson(vars.stance_json, {});
  fillList(root, '.stance', Object.entries(stance), ([label, value]) => {
    const row = div('stance__row');
    row.appendChild(div('stance__label', label));
    row.appendChild(div('stance__value', String(value ?? 0)));
    return row;
  });
  const focus = parseJson(vars.debate_focus_json, []);
  fillList(root, '.debate-list', focus, (item) =>
    div('debate-list__item', typeof item === 'string' ? item : (item.text || item.title || ''))
  );
  const quotes = parseJson(vars.quotes_json, []);
  fillList(root, '.quote-list', quotes, (item) =>
    div('quote-list__item', typeof item === 'string' ? item : (item.text || item.quote || ''))
  );
  return true;
}

function hydrateClosing(host, vars) {
  const root = host.querySelector('.hf-comp-closing');
  if (!root) return false;
  setText(root, '.brand-strip__date', vars.date_label || '');
  setText(root, '.card-title', vars.title || '今日 HN 观察 / 回顾');
  setText(root, '.card-deck', vars.subtitle || '');
  const stories = parseJson(vars.stories_json, []);
  fillList(root, '.story-list', stories, (item, index) => {
    if (typeof item === 'string') return div('story', item);
    const row = div('story');
    const numDiv = div('num-disc', String(item.rank || index + 1));
    const textDiv = div('story__text');
    const zhDiv = div('story__zh', item.title || '');
    const enDiv = div('story__en', item.signal || '');
    textDiv.appendChild(zhDiv);
    textDiv.appendChild(enDiv);
    row.appendChild(numDiv);
    row.appendChild(textDiv);
    return row;
  });
  return true;
}

/* ── hydration loop ── */
function hydrateScenes(attempt = 0) {
  let pending = 0;
  __hfSceneRuntime.forEach((scene) => {
    const host = document.getElementById(scene.host_id);
    if (!host) { pending += 1; return; }
    const vars = scene.variables || {};
    let ok = false;
    if (scene.comp_id === 'cover-card') ok = hydrateCover(host, vars);
    if (scene.comp_id === 'event-card') ok = hydrateEvent(host, vars);
    if (scene.comp_id === 'atmosphere-card') ok = hydrateAtmosphere(host, vars);
    if (scene.comp_id === 'closing-card') ok = hydrateClosing(host, vars);
    if (!ok) pending += 1;
  });
  if (pending && attempt < 120) requestAnimationFrame(() => hydrateScenes(attempt + 1));
}
hydrateScenes();

/* ── story markers on progress bar ── */
__hfStoryMarkers.forEach((marker) => {
  if (!__hfTotalDuration) return;
  const m = document.createElement('span');
  m.className = 'hf-progress__marker';
  m.style.left = Math.max(0, Math.min(100, (Number(marker.start || 0) / __hfTotalDuration) * 100)) + '%';
  progressTrack.appendChild(m);
});

/* ── GSAP root timeline: subtitles, progress, waveform ── */
const rootTl = gsap.timeline({ paused: true });
const cueAt = (time) => __hfSubtitleCues.find(
  (cue) => time >= Number(cue.start || 0) && time < Number(cue.end || 0)
);

rootTl.eventCallback('onUpdate', () => {
  const time = rootTl.time();
  const cue = cueAt(time);
  if (cue) {
    subtitleEl.textContent = cue.text || '';
    subtitleEl.classList.add('is-visible');
  } else {
    subtitleEl.classList.remove('is-visible');
  }
  if (__hfTotalDuration > 0) {
    progressBar.style.width = Math.max(0, Math.min(100, (time / __hfTotalDuration) * 100)) + '%';
  }
  const rate = Number(__hfWaveform.sample_rate || 12);
  const values = __hfWaveform.values || [];
  const base = Math.max(0, Math.floor(time * rate));
  waveBars.forEach((bar, i) => {
    const amp = Number(values[(base + i) % Math.max(1, values.length)] || 0.2);
    bar.style.transform = 'scaleY(' + (0.35 + amp * 1.55).toFixed(3) + ')';
    bar.style.opacity = String(0.34 + amp * 0.56);
  });
});

rootTl.to({}, { duration: __hfTotalDuration || 0.001 });
window.__timelines["hn-techpulse-root"] = rootTl;
