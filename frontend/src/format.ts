export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString();
}

export function statusLabel(status: string): string {
  switch (status) {
    case "processing":
      return "Procesando";
    case "ready":
      return "Listo";
    case "failed":
      return "Fallido";
    default:
      return status;
  }
}
