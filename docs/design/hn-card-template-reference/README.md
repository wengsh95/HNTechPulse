# HN Card Template Reference

This directory preserves the visual reference templates originally iterated in
`tmp/template`.

Use these files as a design and layout reference when developing future
HyperFrames or renderer card implementations. They are not the production render
entry point.

Production HyperFrames compositions live in:

```text
src/providers/renderer/hyperframes/compositions/
```

Reference template structure:

```text
docs/design/hn-card-template-reference/
├── openingcard.html
├── eventcard.html
├── atmospherecard.html
├── closingcard.html
├── index.html
└── design/
    ├── tokens.css
    ├── components.css
    ├── animations.css
    └── render.js
```

Design decisions captured here:

- Unified card shell with warm paper background.
- Shared header: `HN TechPulse / date`.
- Shared title and subtitle treatment via `.card-title` and `.card-deck`.
- Bottom subtitle safe area preserved by `--card-safe-bottom`.
- Event cards use framed content panels and a right-side image.
- Atmosphere cards use three panels: stance distribution, discussion focus,
  and comment highlights.
- Closing cards use the same header and title system as the other cards.

If future development changes the production HyperFrames cards, update this
reference only when the visual system itself changes.
