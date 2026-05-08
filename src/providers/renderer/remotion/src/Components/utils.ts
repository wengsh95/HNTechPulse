/** 通用 Props 接口 */
export interface ElementProps {
  elementProps: Record<string, unknown>;
  duration: number;
  width: number;
  height: number;
}

/** 安全地从 props 取值 */
export function p<T = string>(props: Record<string, unknown>, key: string, fallback: T): T {
  const val = props[key];
  return (val as T) ?? fallback;
}

/** 截断文字 */
export function truncate(text: string, maxLen: number): string {
  if (!text) return "";
  return text.length <= maxLen ? text : text.slice(0, maxLen - 3) + "...";
}

/** 去除 HTML 标签 */
export function stripHtml(text: string): string {
  if (!text) return "";
  return text.replace(/<[^>]+>/g, "");
}
