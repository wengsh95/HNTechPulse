/* ============================================================================
 * Auto-render a card with its embedded sample data when opened directly.
 * The tiny renderer supports the Mustache subset used by these templates.
 * ============================================================================ */
(function () {
  const dataEl = document.getElementById("sample-data");
  if (!dataEl) return;

  let data;
  try {
    data = JSON.parse(dataEl.textContent);
  } catch (error) {
    console.warn("[render] sample-data parse failed:", error);
    return;
  }

  const card = document.querySelector(".card");
  if (!card) return;

  const template = card.outerHTML;
  card.outerHTML = render(template, data);

  function render(tmpl, ctx) {
    const sectionRe = /\{\{\s*#(\w+)\s*\}\}([\s\S]*?)\{\{\s*\/\1\s*\}\}/g;
    const invertedRe = /\{\{\s*\^(\w+)\s*\}\}([\s\S]*?)\{\{\s*\/\1\s*\}\}/g;
    const varRe = /\{\{\s*(\w+)\s*\}\}/g;

    tmpl = tmpl.replace(invertedRe, (_, key, body) => {
      const value = ctx[key];
      const empty = value == null || value === false || (Array.isArray(value) && !value.length);
      return empty ? body : "";
    });

    tmpl = tmpl.replace(sectionRe, (_, key, body) => {
      const value = ctx[key];
      if (Array.isArray(value)) {
        return value
          .map((item) => {
            const itemCtx =
              typeof item === "string" ? { ...ctx, [key]: item } : { ...ctx, ...item };
            return render(body, itemCtx);
          })
          .join("");
      }
      if (value && typeof value === "object") return render(body, { ...ctx, ...value });
      if (value) return render(body, ctx);
      return "";
    });

    return tmpl.replace(varRe, (_, key) => (ctx[key] != null ? String(ctx[key]) : ""));
  }
})();
