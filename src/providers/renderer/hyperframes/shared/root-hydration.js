/*
  Root-level hydration and animation for HyperFrames compositions.

  This file is inlined into the generated root index.html by render_index_html().
  Data injection: Python replaces __HF_DATA_BLOCK__ with const declarations for
  __hfSubtitleCues, __hfStoryMarkers, __hfWaveform, __hfSceneRuntime, __hfTotalDuration.
*/

window.__timelines = window.__timelines || {};

/*
  Pre-register paused stub timelines for the root composition and every
  sub-composition ID we mount. HyperFrames' frame-capture init polls
  `window.__timelines[id]` for each declared `data-composition-id` and
  times out at 45s if any are missing — this used to cost ~46s/chunk
  (8 chunks × 46s = ~370s of pure timeout waste, recovered).

  Why stubs are sufficient:
   - DOM + visual content for each scene is hydrated synchronously by
     this file (hydrateCover/Event/Atmosphere/Closing), not by the
     sub-composition's inline <script>.
   - HyperFrames mounts sub-compositions in a context that doesn't
     reliably propagate `window.__timelines[id] = ...` back to the
     parent window, so cover.html / event.html / atmosphere.html /
     closing.html's own registrations were never visible here — yet
     `cover-card` was the first scene hyperframes polled, so the poll
     timed out before any frame was captured.
   - For static (no-tween) scenes, a paused empty timeline is a valid
     timeline; hyperframes just needs *something* registered.
   - If a sub-composition's script later runs and registers its own
     real timeline, the assignment overwrites the stub — no regression.

  rootTl is replaced at the bottom of this file with the real timeline.
*/
['hn-techpulse-root', 'cover-card', 'event-card', 'atmosphere-card', 'closing-card'].forEach((id) => {
  window.__timelines[id] = window.__timelines[id] || gsap.timeline({ paused: true });
});

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

/* ── card hydration ──
   Each hydrate* function builds the SAME DOM structure the corresponding
   composition's inline <script> produces, so the CSS in compositions/*.html
   (.news-item, .metric-pill, .tag, .stance__fill--*, .focus-item, ...)
   applies. Field names mirror what _extract_variables in hyperframes_props.py
   writes into data-variable-values.
*/
function hydrateCover(host, vars) {
  const root = host.querySelector('.hf-comp-cover');
  if (!root) return false;
  setText(root, '.brand-strip__date', vars.date_label || '');
  setText(root, '.card-title', vars.headline || 'HN 每日观察');
  setText(root, '.card-deck', vars.subtitle || '快讯 / 洞察 / 趋势');
  const lineup = parseJson(vars.lineup_json, []);
  fillList(root, '.opening__list', lineup.slice(0, 3), (it, index) => {
    const item = div('news-item');
    const titleZh = (it && typeof it === 'object')
      ? (it.editor_angle || it.title_translation || it.title_cn || it.original_title || '')
      : String(it || '');
    const titleEn = (it && typeof it === 'object') ? (it.original_title || '') : '';
    item.innerHTML =
      '<div class="num-disc"></div>' +
      '<div class="news-item__info"><div class="news-item__title"></div><div class="news-item__subtitle"></div></div>' +
      '<div class="metrics"><span class="metric-pill"></span><span class="metric-pill"></span></div>';
    item.querySelector('.num-disc').textContent = String((it && it.rank) || index + 1);
    item.querySelector('.news-item__title').textContent = titleZh;
    item.querySelector('.news-item__subtitle').textContent = titleEn;
    const pills = item.querySelectorAll('.metric-pill');
    pills[0].textContent = 'HOT ' + ((it && it.score) || 0);
    pills[1].textContent = 'COM ' + ((it && it.comment_count) || 0);
    return item;
  });
  return true;
}

function hydrateEvent(host, vars) {
  const root = host.querySelector('.hf-comp-event');
  if (!root) return false;
  setText(root, '.brand-strip__date', vars.date_label || '');
  setText(root, '.card-title', vars.title || '');
  // sub_title (English source title) + source_domain share .card-deck; mirror
  // event.html's inline script — drop the whole deck when both are empty.
  const deck = root.querySelector('.card-deck');
  if (deck) {
    if (vars.sub_title || vars.source_domain) {
      setText(deck, '.event-source-title', vars.sub_title || '');
      setText(deck, '.lead__src', vars.source_domain || '');
    } else {
      deck.remove();
    }
  }
  // Metrics: two orange "HOT X" / "COM Y" pills.
  fillList(root, '.metrics', [
    'HOT ' + Number(vars.score || 0),
    'COM ' + Number(vars.comment_count || 0),
  ], (text) => {
    const span = document.createElement('span');
    span.className = 'metric-pill';
    span.textContent = text;
    return span;
  });
  // Tags: rounded outlined chips; remove the container when empty so the
  // metrics row collapses cleanly to the left.
  const tags = parseJson(vars.tags_json, []);
  const tagsEl = root.querySelector('.tags');
  if (tagsEl) {
    if (tags.length) {
      tagsEl.innerHTML = '';
      tags.slice(0, 4).forEach((t) => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = typeof t === 'string' ? t : String(t || '');
        tagsEl.appendChild(span);
      });
    } else {
      tagsEl.remove();
    }
  }
  // Why / Impact: remove the entire section when text is empty (matches the
  // inline-script behavior; setHidden+setText would leave an empty card).
  const why = root.querySelector('.why-section');
  if (why) {
    if (vars.why_it_matters) {
      setText(why, '.section-content', vars.why_it_matters);
    } else {
      why.remove();
    }
  }
  const impact = root.querySelector('.impact-section');
  if (impact) {
    if (vars.impact) {
      setText(impact, '.section-content', vars.impact);
    } else {
      impact.remove();
    }
  }
  // Image: reset then add <img>, or paint a placeholder gradient.
  const imageBox = root.querySelector('.event-image');
  if (imageBox) {
    imageBox.innerHTML = '';
    if (vars.image_src) {
      const img = document.createElement('img');
      img.src = vars.image_src;
      img.alt = vars.title || '';
      imageBox.appendChild(img);
      imageBox.style.background = '';
    } else {
      imageBox.style.background = 'linear-gradient(135deg, #f5eadb 0%, #ead2b6 100%)';
    }
  }
  return true;
}

function hydrateAtmosphere(host, vars) {
  // Composition class is .hf-comp-atmo (NOT .hf-comp-atmosphere) — see
  // compositions/atmosphere.html. The original selector silently no-op'd.
  const root = host.querySelector('.hf-comp-atmo');
  if (!root) return false;
  setText(root, '.brand-strip__date', vars.date_label || '');
  setText(root, '.card-title', vars.title || '');
  const deck = root.querySelector('.card-deck');
  if (deck) {
    if (vars.subtitle) deck.textContent = vars.subtitle;
    else deck.remove();
  }
  // Stance: render three rows in fixed 支持 / 中立 / 质疑 order, normalizing
  // English keys and 0-1 floats to percentages. Each row needs label, percent
  // readout, and a colored .stance__fill bar — the CSS color is keyed off the
  // --support / --neutral / --skeptical modifier class.
  const stance = parseJson(vars.stance_json, {});
  const enToZh = { support: '支持', neutral: '中立', skeptical: '质疑' };
  const fillModifier = {
    '支持': 'stance__fill--support',
    '中立': 'stance__fill--neutral',
    '质疑': 'stance__fill--skeptical',
  };
  const order = ['支持', '中立', '质疑'];
  fillList(root, '.stance', order, (zhKey) => {
    const enKey = Object.keys(enToZh).find((k) => enToZh[k] === zhKey);
    const raw = stance[zhKey] != null ? stance[zhKey] : (stance[enKey] != null ? stance[enKey] : 0);
    const num = Number(raw) || 0;
    const pct = Math.max(0, Math.min(100, num <= 1 ? num * 100 : num));
    const row = div('stance__row');
    row.innerHTML =
      '<div class="stance__label"><span></span><span class="stance__label-val"></span></div>' +
      '<div class="stance__bar"><div class="stance__fill"></div></div>';
    row.querySelector('.stance__label span').textContent = zhKey;
    row.querySelector('.stance__label-val').textContent = Math.round(pct) + '%';
    const fill = row.querySelector('.stance__fill');
    fill.className = 'stance__fill ' + fillModifier[zhKey];
    fill.style.width = pct + '%';
    return row;
  });
  // Debate focus list: orange-bordered .focus-item rows, top 4.
  const focus = parseJson(vars.debate_focus_json, []);
  fillList(root, '.debate-list', focus.slice(0, 4), (item) =>
    div('focus-item', typeof item === 'string' ? item : (item.text || item.title || ''))
  );
  // Quote list: same .focus-item with --quote modifier (italic), top 2.
  const quotes = parseJson(vars.quotes_json, []);
  fillList(root, '.quote-list', quotes.slice(0, 2), (item) => {
    const text = (item && typeof item === 'object')
      ? (item.display_text || item.text_cn || item.text || item.quote || '')
      : String(item || '');
    return div('focus-item focus-item--quote', text);
  });
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
  if (pending && attempt < 30) gsap.delayedCall(0.05, () => hydrateScenes(attempt + 1));
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

/* ── GSAP root timeline: subtitles, progress, waveform ──
   onUpdate is passed via the constructor vars (not .eventCallback) — the
   latter threw `rootTl.eventCallback is not a function` PAGEERROR under
   hyperframes' virtual-time shim, halting this script before line ~301
   and leaving `hn-techpulse-root` unregistered (the 45s poll timeout).
   Constructor vars route through GSAP's own argument parsing and survive
   the shim. `this` inside onUpdate is the Timeline instance.
*/
const cueAt = (time) => __hfSubtitleCues.find(
  (cue) => time >= Number(cue.start || 0) && time < Number(cue.end || 0)
);

const rootTl = gsap.timeline({
  paused: true,
  onUpdate: function () {
    const time = this.time();
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
  },
});

rootTl.to({}, { duration: __hfTotalDuration || 0.001 });
window.__timelines["hn-techpulse-root"] = rootTl;
