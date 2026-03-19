export function info(message: string, meta?: unknown) {
  if (meta !== undefined) {
    console.log(`[api][info] ${new Date().toISOString()} ${message}`, meta);
    return;
  }
  console.log(`[api][info] ${new Date().toISOString()} ${message}`);
}

export function error(message: string, meta?: unknown) {
  if (meta !== undefined) {
    console.error(`[api][error] ${new Date().toISOString()} ${message}`, meta);
    return;
  }
  console.error(`[api][error] ${new Date().toISOString()} ${message}`);
}
