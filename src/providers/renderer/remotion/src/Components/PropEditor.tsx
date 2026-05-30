/* ================================================================
   PropEditor — 递归属性编辑器，动态渲染表单控件
   根据值的类型自动选择: text input / number input / select / nested
   ================================================================ */

import React, { useState, useCallback } from "react";

// ---- 共享样式 ----
const S = {
  fieldset: {
    marginBottom: 2,
    border: "none",
    padding: 0,
  } as React.CSSProperties,
  label: {
    display: "block",
    fontSize: 11,
    fontWeight: 600,
    color: "#8ea8c3",
    marginBottom: 4,
    marginTop: 8,
    letterSpacing: "0.04em",
    textTransform: "uppercase" as const,
  },
  input: {
    width: "100%",
    padding: "6px 10px",
    borderRadius: 5,
    border: "1px solid #2a3a5c",
    background: "#0f3460",
    color: "#e0e0e0",
    fontSize: 13,
    fontFamily: "inherit",
    boxSizing: "border-box" as const,
  },
  textarea: {
    width: "100%",
    padding: "6px 10px",
    borderRadius: 5,
    border: "1px solid #2a3a5c",
    background: "#0f3460",
    color: "#e0e0e0",
    fontSize: 13,
    fontFamily: "inherit",
    boxSizing: "border-box" as const,
    minHeight: 48,
    resize: "vertical" as const,
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 8px",
    background: "rgba(15,52,96,0.5)",
    borderRadius: 4,
    cursor: "pointer",
    marginTop: 6,
    marginBottom: 2,
    fontSize: 12,
    fontWeight: 600,
    color: "#abb9c9",
    userSelect: "none" as const,
  },
  arrayItem: {
    background: "rgba(15,52,96,0.3)",
    borderRadius: 5,
    padding: "8px 10px",
    marginBottom: 4,
    border: "1px solid #1e3a5f",
  },
  btnSmall: {
    padding: "3px 8px",
    borderRadius: 4,
    border: "1px solid #2a3a5c",
    background: "#0f3460",
    color: "#ccc",
    fontSize: 11,
    cursor: "pointer",
    marginRight: 4,
  },
  btnDanger: {
    padding: "3px 8px",
    borderRadius: 4,
    border: "1px solid #5c2a3a",
    background: "#602020",
    color: "#f88",
    fontSize: 11,
    cursor: "pointer",
  },
};

// ---- 类型判断 ----
function isPrimitive(v: unknown): v is string | number | boolean | null | undefined {
  return v === null || v === undefined || typeof v === "string" || typeof v === "number" || typeof v === "boolean";
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// ---- 主编辑器 ----
interface PropEditorProps {
  data: Record<string, unknown>;
  onChange: (newData: Record<string, unknown>) => void;
  /** 可选：每个字段的提示说明 */
  hints?: Record<string, string>;
}

export const PropEditor: React.FC<PropEditorProps> = ({ data, onChange, hints = {} }) => {
  const handleFieldChange = useCallback(
    (key: string, value: unknown) => {
      onChange({ ...data, [key]: value });
    },
    [data, onChange],
  );

  return (
    <div style={{ padding: "0 2px" }}>
      {Object.entries(data).map(([key, value]) => (
        <PropField
          key={key}
          name={key}
          value={value}
          hint={hints[key]}
          onChange={(v) => handleFieldChange(key, v)}
        />
      ))}
    </div>
  );
};

// ---- 单个属性字段 ----
interface PropFieldProps {
  name: string;
  value: unknown;
  hint?: string;
  onChange: (value: unknown) => void;
  /** 嵌套层级，用于缩进 */
  depth?: number;
}

const PropField: React.FC<PropFieldProps> = ({ name, value, hint, onChange, depth = 0 }) => {
  const [collapsed, setCollapsed] = useState(depth > 1); // 深层默认折叠
  const collapsedIcon = collapsed ? "▸" : "▾";

  // null / undefined
  if (value === null || value === undefined) {
    return (
      <div style={{ marginLeft: depth * 8 }}>
        <label style={S.label} title={hint}>{name}</label>
        <input
          style={{ ...S.input, color: "#666" }}
          value={String(value ?? "null")}
          disabled
        />
      </div>
    );
  }

  // boolean
  if (typeof value === "boolean") {
    return (
      <div style={{ marginLeft: depth * 8, display: "flex", alignItems: "center", gap: 8 }}>
        <label style={{ ...S.label, marginTop: 0, marginBottom: 0 }} title={hint}>{name}</label>
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          style={{ accentColor: "#e94560", width: 16, height: 16, cursor: "pointer" }}
        />
      </div>
    );
  }

  // number
  if (typeof value === "number") {
    return (
      <div style={{ marginLeft: depth * 8 }}>
        <label style={S.label} title={hint}>
          {name} <span style={{ fontWeight: 400, color: "#5a8a" }}>{Number.isInteger(value) ? "int" : "float"}</span>
        </label>
        <input
          type="number"
          style={S.input}
          value={value}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            onChange(Number.isNaN(v) ? value : v);
          }}
        />
      </div>
    );
  }

  // string
  if (typeof value === "string") {
    const isLong = value.length > 60;
    const isColor = /^#[0-9a-fA-F]{3,8}$/.test(value);
    if (isColor) {
      return (
        <div style={{ marginLeft: depth * 8, display: "flex", alignItems: "center", gap: 8 }}>
          <label style={{ ...S.label, marginTop: 0, marginBottom: 0 }} title={hint}>{name}</label>
          <input type="color" value={value}
            onChange={(e) => onChange(e.target.value)}
            style={{ width: 28, height: 28, border: "none", borderRadius: 4, cursor: "pointer", padding: 0 }} />
          <input style={{ ...S.input, flex: 1 }} value={value}
            onChange={(e) => onChange(e.target.value)} />
        </div>
      );
    }
    return (
      <div style={{ marginLeft: depth * 8 }}>
        <label style={S.label} title={hint}>{name}</label>
        {isLong ? (
          <textarea style={S.textarea} value={value} onChange={(e) => onChange(e.target.value)} />
        ) : (
          <input style={S.input} value={value} onChange={(e) => onChange(e.target.value)} />
        )}
      </div>
    );
  }

  // object
  if (isObject(value)) {
    const entries = Object.entries(value);
    return (
      <div style={{ marginLeft: depth * 8 }}>
        <div style={S.sectionHeader} onClick={() => setCollapsed(!collapsed)}>
          <span>{collapsedIcon}</span>
          <span>{name}</span>
          <span style={{ fontWeight: 400, color: "#5a8a", fontSize: 10 }}>{`{${entries.length}}`}</span>
        </div>
        {!collapsed && (
          <div style={{ paddingLeft: 8, borderLeft: "1px solid #2a3a5c", marginLeft: 4 }}>
            {entries.map(([k, v]) => (
              <PropField key={k} name={k} value={v} onChange={(newV) => onChange({ ...value, [k]: newV })} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    );
  }

  // array
  if (Array.isArray(value)) {
    const isStringArray = value.every((item) => typeof item === "string");
    return (
      <div style={{ marginLeft: depth * 8 }}>
        <div style={S.sectionHeader} onClick={() => setCollapsed(!collapsed)}>
          <span>{collapsedIcon}</span>
          <span>{name}</span>
          <span style={{ fontWeight: 400, color: "#5a8a", fontSize: 10 }}>
            {isStringArray ? "str" : "obj"}[{value.length}]
          </span>
        </div>
        {!collapsed && (
          <div style={{ paddingLeft: 8, borderLeft: "1px solid #2a3a5c", marginLeft: 4 }}>
            {value.map((item, i) => (
              <div key={i} style={S.arrayItem}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 10, color: "#5a8a", fontWeight: 600 }}>#{i}</span>
                  <button style={S.btnDanger}
                    onClick={() => {
                      const next = [...value];
                      next.splice(i, 1);
                      onChange(next);
                    }}
                  >✕</button>
                </div>
                {isPrimitive(item) ? (
                  <PropField name={`[${i}]`} value={item} onChange={(v) => {
                    const next = [...value];
                    next[i] = v;
                    onChange(next);
                  }} depth={0} />
                ) : isObject(item) ? (
                  Object.entries(item as Record<string, unknown>).map(([k, v]) => (
                    <PropField key={k} name={k} value={v} onChange={(newV) => {
                      const next = [...value];
                      next[i] = { ...(item as Record<string, unknown>), [k]: newV };
                      onChange(next);
                    }} depth={0} />
                  ))
                ) : null}
              </div>
            ))}
            {isStringArray && (
              <button style={{ ...S.btnSmall, marginTop: 4 }}
                onClick={() => onChange([...value, ""])}
              >+ 添加</button>
            )}
            {!isStringArray && (
              <button style={{ ...S.btnSmall, marginTop: 4 }}
                onClick={() => {
                  // 复制第一个元素的结构作为模板
                  const template = value[0] && isObject(value[0])
                    ? Object.fromEntries(Object.keys(value[0] as Record<string, unknown>).map((k) => [k, ""]))
                    : {};
                  onChange([...value, template]);
                }}
              >+ 添加</button>
            )}
          </div>
        )}
      </div>
    );
  }

  // 兜底
  return (
    <div style={{ marginLeft: depth * 8 }}>
      <label style={S.label}>{name}</label>
      <input style={S.input} value={String(value)} disabled />
    </div>
  );
};