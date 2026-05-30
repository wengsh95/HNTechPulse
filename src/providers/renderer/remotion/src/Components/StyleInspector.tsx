/* ================================================================
   StyleInspector — 元素选择器 + 样式覆盖注入
   - 透明 overlay 捕捉鼠标事件
   - hover 高亮元素, click 选中元素
   - 生成 CSS 选择器路径, 支持注入样式覆盖
   - MutationObserver 自动在卡片重渲染后重新应用样式
   ================================================================ */

import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";

/* ---- 可编辑的 CSS 属性定义 ---- */

interface PropDef {
  key: string;
  label: string;
  type: "text" | "number" | "color" | "size" | "range" | "select";
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
}

export const EDITABLE_PROPS: PropDef[] = [
  // 位置
  { key: "position", label: "定位", type: "select", options: ["static", "relative", "absolute", "fixed"] },
  { key: "top", label: "上", type: "text" },
  { key: "left", label: "左", type: "text" },
  { key: "right", label: "右", type: "text" },
  { key: "bottom", label: "下", type: "text" },
  // 尺寸
  { key: "width", label: "宽度", type: "text" },
  { key: "height", label: "高度", type: "text" },
  { key: "maxWidth", label: "最大宽", type: "text" },
  { key: "maxHeight", label: "最大高", type: "text" },
  // 间距
  { key: "marginTop", label: "上外距", type: "text" },
  { key: "marginBottom", label: "下外距", type: "text" },
  { key: "marginLeft", label: "左外距", type: "text" },
  { key: "marginRight", label: "右外距", type: "text" },
  { key: "paddingTop", label: "上内距", type: "text" },
  { key: "paddingBottom", label: "下内距", type: "text" },
  { key: "paddingLeft", label: "左内距", type: "text" },
  { key: "paddingRight", label: "右内距", type: "text" },
  { key: "gap", label: "间距", type: "text" },
  // 文字
  { key: "fontSize", label: "字号", type: "text" },
  { key: "fontWeight", label: "字重", type: "select", options: ["100", "200", "300", "400", "500", "600", "700", "800", "900"] },
  { key: "lineHeight", label: "行高", type: "text" },
  { key: "letterSpacing", label: "字距", type: "text" },
  { key: "textAlign", label: "对齐", type: "select", options: ["left", "center", "right", "justify"] },
  { key: "color", label: "文字色", type: "color" },
  // 外观
  { key: "backgroundColor", label: "背景色", type: "color" },
  { key: "borderRadius", label: "圆角", type: "text" },
  { key: "opacity", label: "透明度", type: "range", min: 0, max: 1, step: 0.05 },
  { key: "transform", label: "变换", type: "text" },
  // 布局
  { key: "display", label: "显示", type: "select", options: ["block", "flex", "inline", "inline-flex", "inline-block", "none"] },
  { key: "flexDirection", label: "Flex方向", type: "select", options: ["row", "column", "row-reverse", "column-reverse"] },
  { key: "alignItems", label: "纵对齐", type: "select", options: ["flex-start", "center", "flex-end", "stretch", "baseline"] },
  { key: "justifyContent", label: "横对齐", type: "select", options: ["flex-start", "center", "flex-end", "space-between", "space-around"] },
];

/* ---- 元素信息 ---- */

export interface ElementInfo {
  tagName: string;
  selector: string;
  /** 元素文本摘要 (最多 40 字符) */
  textSummary: string;
  /** 当前生效的样式覆盖 */
  overrides: Record<string, string>;
}

/* ---- 生成 CSS 选择器路径 (相对于 cardContainer) ---- */

function getSelectorPath(el: Element, root: Element): string {
  const parts: string[] = [];
  let cur: Element | null = el;

  while (cur && cur !== root && cur.parentElement) {
    const parent: Element = cur.parentElement;
    // 找到 cur 在 parent 中的同类元素索引
    const tag = cur.tagName.toLowerCase();
    const siblings = Array.from(parent.children).filter((c) => c.tagName === cur!.tagName);
    const idx = siblings.indexOf(cur);
    if (siblings.length > 1 || idx > 0) {
      parts.unshift(`${tag}:nth-child(${Array.from(parent.children).indexOf(cur) + 1})`);
    } else {
      parts.unshift(tag);
    }
    cur = parent;
  }

  return parts.join(" > ") || el.tagName.toLowerCase();
}

/* ---- 从元素提取文本摘要 ---- */

function getTextSummary(el: Element): string {
  const text = el.textContent?.trim().replace(/\s+/g, " ").slice(0, 40) ?? "";
  return text;
}

/* ---- Props ---- */

interface StyleInspectorProps {
  /** 卡片外层容器 ref (CardPlayer 的 wrapper div) */
  containerRef: React.RefObject<HTMLDivElement | null>;
  /** 是否启用检查模式 */
  enabled: boolean;
  /** 当前选中的元素信息 */
  selectedElement: ElementInfo | null;
  /** 选中元素变化 */
  onSelectElement: (info: ElementInfo | null) => void;
  /** 当前所有样式覆盖 (selector → props) */
  overrides: Record<string, Record<string, string>>;
  /** 覆盖变化 */
  onOverridesChange: (overrides: Record<string, Record<string, string>>) => void;
}

/* ---- 拖拽状态 ---- */

interface DragState {
  type: "move" | "resize";
  dir: string; // nw/n/ne/e/se/s/sw/w
  startMouseX: number; // viewport px
  startMouseY: number;
  startLeft: number; // current override left in px (composition coords)
  startTop: number;
  startWidth: number; // element bounding rect width in px (composition coords)
  startHeight: number;
  el: HTMLElement; // direct DOM ref
}

/* ---- 拖拽把手定义 ---- */

interface HandleDef {
  dir: string;
  cursor: string;
  /** 把手在选框上的位置 (0~1) */
  x: number;
  y: number;
  /** 把手偏移 (使其居中于边角) */
  ox: number;
  oy: number;
}

const HANDLE_SIZE = 10;
const HANDLES: HandleDef[] = [
  { dir: "nw", cursor: "nwse-resize", x: 0, y: 0, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
  { dir: "n", cursor: "ns-resize", x: 0.5, y: 0, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
  { dir: "ne", cursor: "nesw-resize", x: 1, y: 0, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
  { dir: "e", cursor: "ew-resize", x: 1, y: 0.5, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
  { dir: "se", cursor: "nwse-resize", x: 1, y: 1, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
  { dir: "s", cursor: "ns-resize", x: 0.5, y: 1, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
  { dir: "sw", cursor: "nesw-resize", x: 0, y: 1, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
  { dir: "w", cursor: "ew-resize", x: 0, y: 0.5, ox: -HANDLE_SIZE / 2, oy: -HANDLE_SIZE / 2 },
];

/* ---- 辅助: px 字符串转数字 ---- */

function parsePx(v: string | null | undefined): number {
  if (!v) return 0;
  const m = v.match(/^-?[\d.]+/);
  return m ? parseFloat(m[0]) : 0;
}

/* ---- 组件 ---- */

export const StyleInspector: React.FC<StyleInspectorProps> = ({
  containerRef,
  enabled,
  selectedElement,
  onSelectElement,
  overrides,
  onOverridesChange,
}) => {
  const [hoveredRect, setHoveredRect] = useState<DOMRect | null>(null);
  const [selectedRect, setSelectedRect] = useState<DOMRect | null>(null);
  const [hoveredSelector, setHoveredSelector] = useState<string | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);

  const styleTagRef = useRef<HTMLStyleElement | null>(null);
  const dragStartRef = useRef<{ moved: boolean }>({ moved: false });
  const lastOverridesRef = useRef(overrides);
  lastOverridesRef.current = overrides;

  /* ---- 查找卡片根元素 ---- */
  const getCardRoot = useCallback((): Element | null => {
    const container = containerRef.current;
    if (!container) return null;

    let best: Element | null = null;
    let bestScore = 0;

    const allDivs = container.querySelectorAll("div");
    for (const div of allDivs) {
      const el = div as HTMLElement;
      const s = el.style;
      if (s.position !== "relative") continue;
      if (s.overflow !== "hidden") continue;
      if (!el.children.length) continue;
      if (!s.width || !s.height) continue;

      const score = el.getAttribute("style")?.length ?? 0;
      if (score > bestScore) {
        bestScore = score;
        best = el;
      }
    }

    if (!best) {
      for (const div of allDivs) {
        const s = (div as HTMLElement).style;
        if (s.position === "relative" && s.overflow === "hidden" && (div as HTMLElement).children.length > 0) {
          best = div;
          break;
        }
      }
    }

    if (!best) {
      best = container.querySelector("div > div > div > div");
    }

    return best;
  }, [containerRef]);

  /* ---- 获取 composition → viewport 缩放比 ---- */
  const getScaleRatio = useCallback((): number => {
    const container = containerRef.current;
    if (!container) return 1;
    const cw = container.getBoundingClientRect().width;
    return cw > 0 ? cw / 1920 : 1;
  }, [containerRef]);

  /* ---- 通过选择器定位 DOM 元素 ---- */
  const querySelectedEl = useCallback(
    (selector: string): HTMLElement | null => {
      const cardRoot = getCardRoot();
      if (!cardRoot || !selector) return null;
      try {
        return cardRoot.querySelector(selector) as HTMLElement | null;
      } catch {
        return null;
      }
    },
    [getCardRoot],
  );

  /* ---- 更新选中高亮矩形 ---- */
  const refreshSelectedRect = useCallback(() => {
    if (!selectedElement) {
      setSelectedRect(null);
      return;
    }
    const el = querySelectedEl(selectedElement.selector);
    if (!el) return;
    const container = containerRef.current;
    if (!container) return;
    const rect = el.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    setSelectedRect(
      new DOMRect(rect.left - containerRect.left, rect.top - containerRect.top, rect.width, rect.height),
    );
  }, [selectedElement, containerRef, querySelectedEl]);

  // 选中元素变化时刷新矩形
  useEffect(() => {
    refreshSelectedRect();
  }, [selectedElement, refreshSelectedRect]);

  // 覆盖变化时刷新矩形 (因为尺寸可能变了)
  useEffect(() => {
    if (!dragState) refreshSelectedRect();
  }, [overrides, refreshSelectedRect, dragState]);

  /* ---- MutationObserver: 重新注入样式 ---- */
  useEffect(() => {
    if (!enabled) return;
    const container = containerRef.current;
    if (!container) return;

    const reapply = () => {
      if (styleTagRef.current) {
        styleTagRef.current.remove();
        styleTagRef.current = null;
      }
      injectStyles();
      // 非拖拽状态下刷新选中框
      if (!dragState) {
        requestAnimationFrame(() => refreshSelectedRect());
      }
    };

    const observer = new MutationObserver(() => {
      requestAnimationFrame(reapply);
    });

    observer.observe(container, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["style"],
    });

    return () => observer.disconnect();
  }, [enabled, containerRef]); // 不包含 overrides, 避免频繁重建

  /* ---- 注入样式到 DOM ---- */
  const injectStyles = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const currentOverrides = lastOverridesRef.current;

    let css = "";
    for (const [selector, props] of Object.entries(currentOverrides)) {
      if (!selector || Object.keys(props).length === 0) continue;
      const rules = Object.entries(props)
        .filter(([, v]) => v !== "" && v !== null && v !== undefined)
        .map(([k, v]) => `${k}: ${v} !important;`)
        .join(" ");
      if (rules) {
        css += `#style-inspector-root ${selector} { ${rules} }\n`;
      }
    }

    if (!styleTagRef.current) {
      const tag = document.createElement("style");
      tag.id = "style-inspector-dynamic";
      container.appendChild(tag);
      styleTagRef.current = tag;
    }
    styleTagRef.current.textContent = css;

    if (!container.id) {
      container.id = "style-inspector-root";
    }
  }, [containerRef]);

  // 覆盖变化时重新注入
  useEffect(() => {
    if (!enabled) return;
    injectStyles();
  }, [overrides, enabled, injectStyles]);

  /* ================================================================
     鼠标事件处理
     - 非拖拽时: hover 高亮 → click 选中
     - 拖拽时: mousedown 开始 → mousemove 更新 → mouseup 结束
     ================================================================ */

  /* ---- 通用: 获取鼠标下的卡片元素 ---- */
  const getElementAtPoint = useCallback(
    (clientX: number, clientY: number): Element | null => {
      const container = containerRef.current;
      if (!container) return null;
      const cardRoot = getCardRoot();

      // 临时隐藏 overlay 以穿透
      const overlay = container.parentElement?.querySelector("[data-si-overlay]") as HTMLElement | null;
      if (overlay) overlay.style.pointerEvents = "none";

      const elements = document.elementsFromPoint(clientX, clientY);

      if (overlay) overlay.style.pointerEvents = "auto";

      return elements.find((el) => cardRoot?.contains(el) && el !== cardRoot) ?? null;
    },
    [containerRef, getCardRoot],
  );

  /* ---- 选中元素 ---- */
  const selectElementAt = useCallback(
    (clientX: number, clientY: number) => {
      const target = getElementAtPoint(clientX, clientY);
      const container = containerRef.current;
      const cardRoot = getCardRoot();

      if (target && container && cardRoot) {
        const sel = getSelectorPath(target, cardRoot);
        const rect = target.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        setSelectedRect(
          new DOMRect(rect.left - containerRect.left, rect.top - containerRect.top, rect.width, rect.height),
        );
        onSelectElement({
          tagName: target.tagName.toLowerCase(),
          selector: sel,
          textSummary: getTextSummary(target),
          overrides: lastOverridesRef.current[sel] ?? {},
        });
      } else {
        setSelectedRect(null);
        onSelectElement(null);
      }
    },
    [containerRef, getCardRoot, getElementAtPoint, onSelectElement],
  );

  /* ---- mousedown: 可能开始拖拽 ---- */
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!enabled) return;

      // 检查是否点在拖拽把手上
      const handleEl = (e.target as HTMLElement).closest("[data-si-handle]");
      if (handleEl && selectedElement) {
        e.preventDefault();
        e.stopPropagation();
        const dir = handleEl.getAttribute("data-si-handle")!;
        const el = querySelectedEl(selectedElement.selector);
        if (!el) return;

        const rect = el.getBoundingClientRect();
        const scale = getScaleRatio();

        // 已有覆盖值
        const ov = lastOverridesRef.current[selectedElement.selector] ?? {};

        // 确保 position: relative
        if (!ov.position) {
          const next = { ...lastOverridesRef.current };
          if (!next[selectedElement.selector]) next[selectedElement.selector] = {};
          next[selectedElement.selector] = { ...next[selectedElement.selector], position: "relative" };
          onOverridesChange(next);
        }

        setDragState({
          type: "resize",
          dir,
          startMouseX: e.clientX,
          startMouseY: e.clientY,
          startLeft: parsePx(ov.left) || 0,
          startTop: parsePx(ov.top) || 0,
          startWidth: rect.width / scale,
          startHeight: rect.height / scale,
          el,
        });
        dragStartRef.current.moved = false;
        return;
      }

      // 检查是否点在已选中元素上 → 开始移动拖拽
      const target = getElementAtPoint(e.clientX, e.clientY);
      if (target && selectedElement) {
        const cardRoot = getCardRoot();
        const sel = getSelectorPath(target, cardRoot!);
        if (sel === selectedElement.selector) {
          e.preventDefault();
          e.stopPropagation();
          const el = querySelectedEl(selectedElement.selector);
          if (!el) return;

          const ov = lastOverridesRef.current[selectedElement.selector] ?? {};

          // 确保 position: relative
          if (!ov.position) {
            const next = { ...lastOverridesRef.current };
            if (!next[selectedElement.selector]) next[selectedElement.selector] = {};
            next[selectedElement.selector] = { ...next[selectedElement.selector], position: "relative" };
            onOverridesChange(next);
          }

          setDragState({
            type: "move",
            dir: "move",
            startMouseX: e.clientX,
            startMouseY: e.clientY,
            startLeft: parsePx(ov.left) || 0,
            startTop: parsePx(ov.top) || 0,
            startWidth: 0,
            startHeight: 0,
            el,
          });
          dragStartRef.current.moved = false;
          return;
        }
      }

      // 否则: 选中元素
      dragStartRef.current.moved = false;
      selectElementAt(e.clientX, e.clientY);
    },
    [
      enabled,
      selectedElement,
      querySelectedEl,
      getCardRoot,
      getScaleRatio,
      getElementAtPoint,
      selectElementAt,
      onOverridesChange,
    ],
  );

  /* ---- mousemove: 拖拽更新 或 高亮 ---- */
  const handleMouseMove = useCallback(
    (e: React.MouseEvent | { clientX: number; clientY: number }) => {
      if (!enabled) return;

      if (dragState) {
        dragStartRef.current.moved = true;
        const scale = getScaleRatio();
        const dx = (e.clientX - dragState.startMouseX) / scale;
        const dy = (e.clientY - dragState.startMouseY) / scale;
        const el = dragState.el;

        if (dragState.type === "move") {
          el.style.position = "relative";
          el.style.left = `${dragState.startLeft + dx}px`;
          el.style.top = `${dragState.startTop + dy}px`;
          refreshSelectedRect();
        } else {
          const d = dragState;
          let newLeft = d.startLeft;
          let newTop = d.startTop;
          let newW = d.startWidth;
          let newH = d.startHeight;

          if (d.dir.includes("e")) newW = Math.max(4, d.startWidth + dx);
          if (d.dir.includes("w")) { newW = Math.max(4, d.startWidth - dx); newLeft = d.startLeft + dx; }
          if (d.dir.includes("s")) newH = Math.max(4, d.startHeight + dy);
          if (d.dir.includes("n")) { newH = Math.max(4, d.startHeight - dy); newTop = d.startTop + dy; }

          el.style.position = "relative";
          el.style.width = `${newW}px`;
          el.style.height = `${newH}px`;
          if (d.dir.includes("w") || d.dir === "n" || d.dir === "s") {
            el.style.left = `${newLeft}px`;
          }
          if (d.dir.includes("n") || d.dir === "w" || d.dir === "e") {
            el.style.top = `${newTop}px`;
          }
          refreshSelectedRect();
        }
        return;
      }

      // 非拖拽: 高亮元素 (仅响应 overlay 事件)
      if (!("currentTarget" in e)) return;
      const container = containerRef.current;
      if (!container) return;

      const target = getElementAtPoint(e.clientX, e.clientY);
      if (target) {
        const rect = target.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        setHoveredRect(
          new DOMRect(rect.left - containerRect.left, rect.top - containerRect.top, rect.width, rect.height),
        );
        const cardRoot = getCardRoot();
        if (cardRoot) {
          setHoveredSelector(getSelectorPath(target, cardRoot));
        }
      } else {
        setHoveredRect(null);
        setHoveredSelector(null);
      }
    },
    [enabled, dragState, containerRef, getCardRoot, getScaleRatio, getElementAtPoint, refreshSelectedRect],
  );

  /* ---- 全局 mousemove: 拖拽时即使鼠标移出 overlay 也能跟踪 ---- */
  useEffect(() => {
    if (!dragState) return;
    const onGlobalMove = (e: MouseEvent) => {
      e.preventDefault(); // 阻止页面滚动
      handleMouseMove(e);
    };
    window.addEventListener("mousemove", onGlobalMove, { passive: false });
    return () => window.removeEventListener("mousemove", onGlobalMove);
  }, [dragState, handleMouseMove]);

  /* ---- 拖拽时锁定外层可滚动容器 ---- */
  useEffect(() => {
    if (!dragState || !containerRef.current) return;
    // 向上查找第一个 overflow:auto 或 scroll 的祖先
    let el: HTMLElement | null = containerRef.current.parentElement;
    while (el) {
      const ov = el.style.overflow || getComputedStyle(el).overflow;
      if (ov === "auto" || ov === "scroll") break;
      el = el.parentElement;
    }
    if (!el) return;
    const prev = el.style.overflow;
    el.style.overflow = "hidden";
    return () => { el.style.overflow = prev; };
  }, [dragState, containerRef]);

  /* ---- 结束拖拽的通用逻辑 ---- */
  const finishDrag = useCallback(
    (clientX: number, clientY: number) => {
      if (!dragState) return;

      const scale = getScaleRatio();
      const dx = (clientX - dragState.startMouseX) / scale;
      const dy = (clientY - dragState.startMouseY) / scale;

      const newLeft = Math.round(dragState.startLeft + (dragState.type === "move" ? dx : 0));
      const newTop = Math.round(dragState.startTop + (dragState.type === "move" ? dy : 0));

      let newW = dragState.startWidth;
      let newH = dragState.startHeight;
      let finalLeft = newLeft;
      let finalTop = newTop;

      if (dragState.type === "resize") {
        const d = dragState;
        if (d.dir.includes("e")) newW = Math.max(4, d.startWidth + dx);
        if (d.dir.includes("w")) { newW = Math.max(4, d.startWidth - dx); finalLeft = d.startLeft + dx; }
        if (d.dir.includes("s")) newH = Math.max(4, d.startHeight + dy);
        if (d.dir.includes("n")) { newH = Math.max(4, d.startHeight - dy); finalTop = d.startTop + dy; }
      }

      const sel = selectedElement?.selector;
      if (sel) {
        const next = { ...lastOverridesRef.current };
        if (!next[sel]) next[sel] = {};

        if (dragState.type === "move") {
          next[sel] = {
            ...next[sel],
            position: "relative",
            left: `${Math.round(newLeft)}px`,
            top: `${Math.round(newTop)}px`,
          };
        } else {
          const updates: Record<string, string> = { position: "relative" };
          updates.width = `${Math.round(newW)}px`;
          updates.height = `${Math.round(newH)}px`;
          if (Math.abs(Math.round(finalLeft)) > 0) updates.left = `${Math.round(finalLeft)}px`;
          if (Math.abs(Math.round(finalTop)) > 0) updates.top = `${Math.round(finalTop)}px`;
          next[sel] = { ...next[sel], ...updates };
        }

        onOverridesChange(next);
      }

      setDragState(null);
      setTimeout(() => refreshSelectedRect(), 50);
    },
    [dragState, selectedElement, getScaleRatio, onOverridesChange, refreshSelectedRect],
  );

  /* ---- mouseup on overlay: 结束拖拽 ---- */
  const handleMouseUp = useCallback(
    (e: React.MouseEvent) => {
      if (!dragState) return;
      finishDrag(e.clientX, e.clientY);
    },
    [dragState, finishDrag],
  );

  /* ---- 全局 mouseup: 拖拽到 overlay 外时也要结束 ---- */
  useEffect(() => {
    if (!dragState) return;
    const onGlobalUp = (e: MouseEvent) => {
      finishDrag(e.clientX, e.clientY);
    };
    window.addEventListener("mouseup", onGlobalUp);
    return () => window.removeEventListener("mouseup", onGlobalUp);
  }, [dragState, finishDrag]);

  /* ---- 鼠标离开 ---- */
  const handleMouseLeave = useCallback(() => {
    setHoveredRect(null);
    setHoveredSelector(null);
    // 拖拽中不取消
  }, []);

  /* ================================================================
     渲染
     ================================================================ */

  if (!enabled) return null;

  return (
    <>
      {/* 透明捕获层 */}
      <div
        data-si-overlay
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 999,
          cursor: dragState
            ? dragState.type === "move"
              ? "grabbing"
              : HANDLES.find((h) => h.dir === dragState.dir)?.cursor ?? "crosshair"
            : selectedElement
              ? "grab"
              : "crosshair",
        }}
      />

      {/* Hover 高亮 (非拖拽时显示) */}
      {hoveredRect && !dragState && (
        <div
          style={{
            position: "absolute",
            left: hoveredRect.x,
            top: hoveredRect.y,
            width: hoveredRect.width,
            height: hoveredRect.height,
            border: "1.5px dashed #e94560",
            backgroundColor: "rgba(233, 69, 96, 0.08)",
            pointerEvents: "none",
            zIndex: 998,
            boxSizing: "border-box",
            transition: "all 0.05s",
          }}
        >
          {hoveredSelector && (
            <span
              style={{
                position: "absolute",
                bottom: "100%",
                left: 0,
                background: "#e94560",
                color: "#fff",
                fontSize: 10,
                fontFamily: "monospace",
                padding: "1px 6px",
                borderRadius: 3,
                whiteSpace: "nowrap",
                marginBottom: 2,
                maxWidth: 300,
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {hoveredSelector}
            </span>
          )}
        </div>
      )}

      {/* 选中高亮 */}
      {selectedRect && (
        <div
          style={{
            position: "absolute",
            left: selectedRect.x,
            top: selectedRect.y,
            width: selectedRect.width,
            height: selectedRect.height,
            border: `2px solid ${dragState ? "#e94560" : "#00d4aa"}`,
            backgroundColor: dragState
              ? "rgba(233, 69, 96, 0.08)"
              : "rgba(0, 212, 170, 0.06)",
            pointerEvents: "none",
            zIndex: 998,
            boxSizing: "border-box",
          }}
        />
      )}

      {/* 拖拽把手 — 必须独立于选中框并高于 overlay (z-index:999) 才能接收点击 */}
      {selectedRect &&
        HANDLES.map((h) => (
          <div
            key={h.dir}
            data-si-handle={h.dir}
            style={{
              position: "absolute",
              left:
                h.x === 0
                  ? selectedRect.x + h.ox
                  : h.x === 1
                    ? selectedRect.x + selectedRect.width + h.ox
                    : selectedRect.x + selectedRect.width * h.x + h.ox,
              top:
                h.y === 0
                  ? selectedRect.y + h.oy
                  : h.y === 1
                    ? selectedRect.y + selectedRect.height + h.oy
                    : selectedRect.y + selectedRect.height * h.y + h.oy,
              width: HANDLE_SIZE,
              height: HANDLE_SIZE,
              background: "#fff",
              border: `2px solid ${dragState ? "#e94560" : "#00d4aa"}`,
              borderRadius: 2,
              cursor: h.cursor,
              zIndex: 1000,
              boxSizing: "border-box",
            }}
          />
        ))}

      <CleanupOnDisable enabled={enabled} containerRef={containerRef} />
    </>
  );
};

/* ---- 禁用时清理注入的样式 ---- */

function CleanupOnDisable({
  enabled,
  containerRef,
}: {
  enabled: boolean;
  containerRef: React.RefObject<HTMLDivElement | null>;
}) {
  useEffect(() => {
    if (enabled) return;
    // 禁用时移除注入的样式
    const tag = document.getElementById("style-inspector-dynamic");
    if (tag) tag.remove();
    const root = document.getElementById("style-inspector-root");
    if (root) root.removeAttribute("id");
  }, [enabled, containerRef]);

  return null;
}

/* ---- 对外暴露的 styleOverride API (通过 module-level) ---- */

// 导出一个简单的 StyleEditor 组件用于左侧面板
interface StyleEditorPanelProps {
  element: ElementInfo | null;
  overrides: Record<string, Record<string, string>>;
  onUpdateProp: (selector: string, prop: string, value: string) => void;
  onClearElement: (selector: string) => void;
}

const DARK = {
  bg: "#121926",
  panel: "#16213e",
  input: "#0f3460",
  border: "#1e3a5f",
  accent: "#e94560",
  text: "#e0e0e0",
  muted: "#8ea8c3",
  dim: "#4a6078",
};

export const StyleEditorPanel: React.FC<StyleEditorPanelProps> = ({
  element,
  overrides,
  onUpdateProp,
  onClearElement,
}) => {
  if (!element) {
    return (
      <div style={{ padding: "16px 0", color: DARK.dim, fontSize: 13, textAlign: "center" }}>
        👆 点击卡片上的元素以选中
        <div style={{ marginTop: 8, fontSize: 11, color: DARK.dim }}>
          选中后可编辑位置、大小、颜色等 CSS 属性
        </div>
      </div>
    );
  }

  const currentOverrides = overrides[element.selector] ?? {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {/* 元素信息 */}
      <div
        style={{
          padding: "8px 10px",
          background: "rgba(0,212,170,0.1)",
          borderRadius: 6,
          marginBottom: 8,
          border: "1px solid rgba(0,212,170,0.25)",
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 700, color: "#00d4aa", fontFamily: "monospace", marginBottom: 2 }}>
          &lt;{element.tagName}&gt;
        </div>
        <div style={{ fontSize: 10, color: DARK.muted, fontFamily: "monospace", wordBreak: "break-all", marginBottom: 4 }}>
          {element.selector}
        </div>
        {element.textSummary && (
          <div style={{ fontSize: 11, color: DARK.text, opacity: 0.7, fontStyle: "italic" }}>
            &ldquo;{element.textSummary}&rdquo;
          </div>
        )}
        <button
          onClick={() => onClearElement(element.selector)}
          style={{
            marginTop: 6,
            padding: "3px 10px",
            borderRadius: 4,
            border: `1px solid ${DARK.border}`,
            background: "transparent",
            color: DARK.muted,
            fontSize: 10,
            cursor: "pointer",
          }}
        >
          ✕ 清除此元素样式
        </button>
      </div>

      {/* CSS 属性编辑 */}
      <div style={{ maxHeight: "calc(100vh - 260px)", overflowY: "auto", paddingRight: 4 }}>
        {EDITABLE_PROPS.map((def) => {
          const currentVal = currentOverrides[def.key] ?? "";

          return (
            <div
              key={def.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginBottom: 4,
                padding: "2px 0",
              }}
            >
              <label
                style={{
                  fontSize: 10,
                  fontFamily: "monospace",
                  color: currentVal ? DARK.accent : DARK.muted,
                  width: 56,
                  minWidth: 56,
                  textAlign: "right",
                  fontWeight: currentVal ? 600 : 400,
                }}
              >
                {def.label}
              </label>

              {def.type === "select" && def.options ? (
                <select
                  value={currentVal}
                  onChange={(e) => onUpdateProp(element.selector, def.key, e.target.value)}
                  style={{
                    flex: 1,
                    padding: "3px 6px",
                    borderRadius: 3,
                    border: `1px solid ${currentVal ? DARK.accent : DARK.border}`,
                    background: DARK.input,
                    color: currentVal ? DARK.accent : DARK.text,
                    fontSize: 11,
                    fontFamily: "monospace",
                  }}
                >
                  <option value="">(默认)</option>
                  {def.options.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : def.type === "color" ? (
                <div style={{ display: "flex", gap: 4, flex: 1, alignItems: "center" }}>
                  <input
                    type="color"
                    value={currentVal || "#000000"}
                    onChange={(e) => onUpdateProp(element.selector, def.key, e.target.value)}
                    style={{
                      width: 24,
                      height: 24,
                      border: `1px solid ${currentVal ? DARK.accent : DARK.border}`,
                      borderRadius: 3,
                      cursor: "pointer",
                      padding: 0,
                      background: "none",
                    }}
                  />
                  <input
                    type="text"
                    value={currentVal}
                    onChange={(e) => onUpdateProp(element.selector, def.key, e.target.value)}
                    placeholder="(默认)"
                    style={{
                      flex: 1,
                      padding: "3px 6px",
                      borderRadius: 3,
                      border: `1px solid ${currentVal ? DARK.accent : DARK.border}`,
                      background: DARK.input,
                      color: currentVal ? DARK.accent : DARK.text,
                      fontSize: 11,
                      fontFamily: "monospace",
                      width: 70,
                    }}
                  />
                </div>
              ) : def.type === "range" ? (
                <div style={{ display: "flex", gap: 4, flex: 1, alignItems: "center" }}>
                  <input
                    type="range"
                    min={def.min ?? 0}
                    max={def.max ?? 1}
                    step={def.step ?? 0.05}
                    value={currentVal || "0"}
                    onChange={(e) => onUpdateProp(element.selector, def.key, e.target.value)}
                    style={{ flex: 1, accentColor: DARK.accent }}
                  />
                  <span style={{ fontSize: 10, color: DARK.muted, width: 30, textAlign: "right" }}>
                    {currentVal || "0"}
                  </span>
                </div>
              ) : (
                <input
                  type="text"
                  value={currentVal}
                  onChange={(e) => onUpdateProp(element.selector, def.key, e.target.value)}
                  placeholder="(默认)"
                  style={{
                    flex: 1,
                    padding: "3px 6px",
                    borderRadius: 3,
                    border: `1px solid ${currentVal ? DARK.accent : DARK.border}`,
                    background: DARK.input,
                    color: currentVal ? DARK.accent : DARK.text,
                    fontSize: 11,
                    fontFamily: "monospace",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
