import { hasTelugu, plainText } from '@/lib/script';
import { checkHealth } from '@/lib/health';

describe('script helpers', () => {
  test('detects Telugu script only', () => {
    expect(hasTelugu('మీరు చెప్పే వరకు')).toBe(true);
    expect(hasTelugu('mirru cheppe varaku')).toBe(false);
    expect(hasTelugu('biryani దొరుకుతుందా?')).toBe(true);
    expect(hasTelugu('')).toBe(false);
  });

  test('plainText flattens strings, numbers and arrays', () => {
    expect(plainText(['Total ', 588])).toBe('Total 588');
    expect(plainText(null)).toBe('');
  });
});

describe('checkHealth', () => {
  const res = (status: string, ok = true) => ({ ok, json: async () => ({ status }) }) as unknown as Response;

  test('ok when the backend says ok', async () => {
    const onWaking = jest.fn();
    expect(await checkHealth(onWaking, { fetchImpl: async () => res('ok') })).toBe('ok');
    expect(onWaking).not.toHaveBeenCalled();
  });

  test('down on a network error, never throws', async () => {
    const fail = async () => {
      throw new Error('network');
    };
    expect(await checkHealth(() => {}, { fetchImpl: fail as unknown as typeof fetch })).toBe('down');
  });

  test('down on a wrong body or non-200', async () => {
    expect(await checkHealth(() => {}, { fetchImpl: async () => res('error') })).toBe('down');
    expect(await checkHealth(() => {}, { fetchImpl: async () => res('ok', false) })).toBe('down');
  });

  test('calls onWaking when the answer is slow', async () => {
    jest.useFakeTimers();
    const onWaking = jest.fn();
    let resolve!: (r: Response) => void;
    const slow = () => new Promise<Response>((r) => (resolve = r));
    const p = checkHealth(onWaking, { slowMs: 4000, fetchImpl: slow as unknown as typeof fetch });
    jest.advanceTimersByTime(4001);
    expect(onWaking).toHaveBeenCalledTimes(1);
    resolve(res('ok'));
    expect(await p).toBe('ok');
    jest.useRealTimers();
  });
});
