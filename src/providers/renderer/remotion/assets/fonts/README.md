# Fonts (vendored)

本目录下的 woff2 字体文件随项目提交，用于 Remotion 渲染时本地化加载，**避免**渲染机
器联网下载 Google Fonts 导致的字形不一致（详见 [src/Root.tsx](../../src/Root.tsx)
的字体加载逻辑，以及 [tokens.ts](../../src/Components/tokens.ts) 的字体栈）。

prepare_render 步骤会把这里的所有 `.woff2` 拷贝到
`data/{date}/render/remotion/public/fonts/`，Remotion CLI 通过
`--public-dir=...` 把它们暴露给 `staticFile("fonts/...")`。

## 文件清单

| 文件 | 覆盖范围 | 大小 |
|---|---|---|
| `Fraunces-VF-latin.woff2` | 西文（Latin）— variable font，覆盖 500/700/900 全部 weight | 36 KB |
| `JetBrainsMono-VF-latin.woff2` | 西文（Latin）— variable font，覆盖 500/600/700 全部 weight | 40 KB |
| `NotoSansSC-Regular.woff2` | 简体中文 sans-serif，weight 400 | 1.1 MB |
| `NotoSansSC-Bold.woff2` | 简体中文 sans-serif，weight 700 | 1.1 MB |
| `NotoSerifSC-Regular.woff2` | 简体中文 serif，weight 400 | 1.5 MB |
| `NotoSerifSC-Bold.woff2` | 简体中文 serif，weight 700 | 1.5 MB |

合计约 5.3 MB。

## 字体来源与许可

全部字体均使用 **SIL Open Font License v1.1 (OFL)**，许可证全文见 [OFL.txt](OFL.txt)，
可自由商用，禁止单独售卖字体本身，需保留原版权信息。

- **Fraunces** — 上游 https://github.com/undercase/Fraunces，© The Fraunces Project Authors
- **JetBrains Mono** — 上游 https://github.com/JetBrains/JetBrainsMono，© 2020 The JetBrains Mono Project Authors
- **Noto Sans SC / Noto Serif SC** — 上游 https://github.com/notofonts/noto-cjk，© Google LLC

下载源（woff2 已由 fontsource 转码、保留 OFL）：
- jsDelivr CDN: `https://cdn.jsdelivr.net/fontsource/fonts/{family}@latest/...`

## 添加新字体的步骤

1. 把 woff2 放进本目录。
2. 在 [src/Root.tsx](../../src/Root.tsx) 的 `FONT_FILES` 数组里加一行
   `{ family, weight, file }` —— `family` 必须与
   [tokens.ts](../../src/Components/tokens.ts) 的 `FONTS` 字体栈中的字符串完全一致。
3. 跑一次 `prepare_render`，确认 `data/{date}/render/remotion/public/fonts/`
   出现了新文件。
