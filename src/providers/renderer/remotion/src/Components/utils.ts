/** Shared props for Remotion scene elements. */
export interface ElementProps {
  elementProps: Record<string, unknown>;
  duration: number;
  width: number;
  height: number;
}

/** Safely read a value from element props with runtime type validation. */
export function p<T = string>(props: Record<string, unknown>, key: string, fallback: T): T {
  const val = props[key];
  if (val === undefined || val === null) return fallback;
  if (typeof fallback === "number")
    return (typeof val === "number" ? val : Number(val) || fallback) as T;
  if (typeof fallback === "string") return (typeof val === "string" ? val : String(val)) as T;
  if (typeof fallback === "boolean") return (typeof val === "boolean" ? val : Boolean(val)) as T;
  return val as T;
}

export function stripHtml(text: string): string {
  if (!text) return "";
  return String(text).replace(/<[^>]*>/g, "");
}
