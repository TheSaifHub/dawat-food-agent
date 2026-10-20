import { API_URL } from './config';

export type Health = 'checking' | 'ok' | 'waking' | 'down';

/**
 * Checks GET /health. Calls onWaking if the first answer takes longer than `slowMs`
 * ("Waking up Dawat AI…" on a free-tier cold start). Never throws.
 */
export async function checkHealth(
  onWaking: () => void,
  opts: { slowMs?: number; timeoutMs?: number; fetchImpl?: typeof fetch } = {},
): Promise<'ok' | 'down'> {
  const { slowMs = 4000, timeoutMs = 70000, fetchImpl = fetch } = opts;
  const controller = new AbortController();
  const slow = setTimeout(onWaking, slowMs);
  const abort = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchImpl(`${API_URL}/health`, { signal: controller.signal });
    const body = (await res.json()) as { status?: string };
    return res.ok && body.status === 'ok' ? 'ok' : 'down';
  } catch {
    return 'down';
  } finally {
    clearTimeout(slow);
    clearTimeout(abort);
  }
}
