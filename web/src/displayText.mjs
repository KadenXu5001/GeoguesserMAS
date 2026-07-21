export function capitalizeHintText(value) {
  if (typeof value !== "string") return "";
  const text = value.trim();
  if (!text) return "";
  return text[0].toLocaleUpperCase() + text.slice(1);
}
