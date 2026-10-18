// Only immutable responses are reused. Writes isolate in-flight reads by generation.
const pending = new Map<string, Promise<unknown>>();
const saved = new Map<string, { value: unknown; expires: number }>();
let generation = 0;
export const DATA_CHANGED = "portfolio-data-changed";

export function invalidateReads(notify = false) {
  generation++;
  saved.clear();
  pending.clear();
  if (notify) window.dispatchEvent(new Event(DATA_CHANGED));
}

export function cachedRead<T>(key: string, read: () => Promise<T>, ttl = 0): Promise<T> {
  const stored = saved.get(key);
  if (stored && stored.expires > Date.now()) return Promise.resolve(stored.value as T);
  saved.delete(key);
  const existing = pending.get(key);
  if (existing) return existing as Promise<T>;
  const started = generation;
  const promise = read().then(value => {
    if (started === generation && ttl > 0) {
      if (saved.size >= 64) saved.delete(saved.keys().next().value!);
      saved.set(key, { value, expires: Date.now() + ttl });
    }
    return value;
  }).finally(() => { if (pending.get(key) === promise) pending.delete(key); });
  pending.set(key, promise);
  return promise;
}
