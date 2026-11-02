import { describe, expect, it } from 'vitest';
import { systemClock } from '../src/ports';
import {
  createFakeClock,
  createFakeConnectivity,
  createFakeVisibility,
  createMemoryStorage,
} from '../src/testing';

describe('in-memory port adapters', () => {
  it('memory storage gets, sets, deletes and lists keys by prefix', async () => {
    const s = createMemoryStorage();
    expect(await s.get('a')).toBeNull();
    await s.set('a:1', 'x');
    await s.set('b:1', 'y');
    expect(await s.get('a:1')).toBe('x');
    expect(await s.keys('a:')).toEqual(['a:1']);
    expect((await s.keys()).sort()).toEqual(['a:1', 'b:1']);
    await s.delete('a:1');
    expect(await s.keys('a:')).toEqual([]);
  });

  it('fake clock fires due timers in order and honours clearTimeout', async () => {
    const c = createFakeClock(1000);
    const fired: string[] = [];
    c.setTimeout(() => fired.push('b'), 20);
    c.setTimeout(() => fired.push('a'), 10);
    const h = c.setTimeout(() => fired.push('never'), 15);
    c.setTimeout(() => fired.push('neg'), -5);
    c.clearTimeout(h);
    expect(c.pending()).toBe(3);
    await c.advance(10);
    expect(fired).toEqual(['neg', 'a']);
    expect(c.now()).toBe(1010);
    await c.advance(100);
    expect(fired).toEqual(['neg', 'a', 'b']);
    expect(c.now()).toBe(1110);
  });

  it('fake connectivity and visibility notify subscribers only on change', () => {
    const net = createFakeConnectivity(false);
    const vis = createFakeVisibility();
    const seen: boolean[] = [];
    const off = net.port.subscribe((v) => seen.push(v));
    vis.port.subscribe((v) => seen.push(v));
    net.set(false);
    net.set(true);
    vis.set(false);
    off();
    net.set(false);
    expect(seen).toEqual([true, false]);
    expect(net.port.isOnline()).toBe(false);
    expect(vis.port.isVisible()).toBe(false);
  });

  it('system clock wraps host timers', async () => {
    const c = systemClock();
    expect(Math.abs(c.now() - Date.now())).toBeLessThan(1000);
    const fired = await new Promise<boolean>((resolve) => {
      const h = c.setTimeout(() => resolve(false), 5);
      c.clearTimeout(h);
      c.setTimeout(() => resolve(true), 1);
    });
    expect(fired).toBe(true);
  });
});
