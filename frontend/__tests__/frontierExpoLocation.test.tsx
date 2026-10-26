/** GF-P0-115: expo-location adapter + FrontierLocationProvider (jest, mocked native). */
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

const mockAppStateListeners: ((s: string) => void)[] = [];
jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  AppState: {
    addEventListener: (_: string, cb: (s: string) => void) => {
      mockAppStateListeners.push(cb);
      return { remove: () => mockAppStateListeners.splice(mockAppStateListeners.indexOf(cb), 1) };
    },
  },
}), { virtual: true });

type Cb = (l: unknown) => void;
type MockLoc = any; // eslint-disable-line @typescript-eslint/no-explicit-any
const mockLoc: MockLoc = {
  Accuracy: { High: 4, BestForNavigation: 6 },
  hasServicesEnabledAsync: jest.fn(async () => true),
  getForegroundPermissionsAsync: jest.fn(async () => ({ status: "undetermined", granted: false, canAskAgain: true })),
  requestForegroundPermissionsAsync: jest.fn(async () => ({ status: "granted", granted: true, canAskAgain: true })),
  remove: jest.fn(),
  cb: null as Cb | null,
  err: null as ((r: string) => void) | null,
  watchPositionAsync: jest.fn(async (_o: unknown, cb: Cb, err?: (r: string) => void): Promise<{ remove: () => void }> => {
    mockLoc.cb = cb;
    mockLoc.err = err ?? null;
    return { remove: mockLoc.remove };
  }),
};
jest.mock("expo-location", () => mockLoc, { virtual: true });

import { createExpoLocationAdapter, loadExpoLocation, toFrontierFix, FrontierLocationError } from "../src/product/location/expoLocationAdapter";
import { FrontierLocationProvider, useFrontierLocation, type FrontierLocationApi } from "../src/product/location/FrontierLocationProvider";

const loc = (over: Partial<{ accuracy: number | null; timestamp: number; mocked: boolean; latitude: number }> = {}) => ({
  coords: { latitude: over.latitude ?? 59.91, longitude: 10.75, altitude: 12, accuracy: over.accuracy === undefined ? 5 : over.accuracy, altitudeAccuracy: 3 },
  timestamp: over.timestamp ?? Date.now(),
  mocked: over.mocked,
});

beforeEach(() => {
  jest.clearAllMocks();
  mockLoc.cb = null;
  mockLoc.getForegroundPermissionsAsync.mockResolvedValue({ status: "undetermined", granted: false, canAskAgain: true });
  mockLoc.requestForegroundPermissionsAsync.mockResolvedValue({ status: "granted", granted: true, canAskAgain: true });
  mockLoc.hasServicesEnabledAsync.mockResolvedValue(true);
});

describe("expo-location adapter", () => {
  it("loads the mocked module", () => expect(loadExpoLocation()).toBe(mockLoc));
  it("maps an Expo location to a Frontier fix", () => {
    const f = toFrontierFix(loc() as never);
    expect(f).toMatchObject({ latitude_deg: 59.91, longitude_deg: 10.75, horizontal_accuracy_m: 5, source: "host_os_gnss" });
    expect(Number.isNaN(toFrontierFix(loc({ accuracy: null }) as never).horizontal_accuracy_m)).toBe(true);
  });
  it("requests foreground permission only (never background)", async () => {
    const a = createExpoLocationAdapter(mockLoc);
    await expect(a.requestForegroundPermission()).resolves.toBe(true);
    expect(mockLoc.requestForegroundPermissionsAsync).toHaveBeenCalledTimes(1);
    expect(a.lastPermission()).toBe("granted");
    expect((mockLoc as Record<string, unknown>).requestBackgroundPermissionsAsync).toBeUndefined();
  });
  it("skips the prompt when already granted, and when blocked", async () => {
    mockLoc.getForegroundPermissionsAsync.mockResolvedValueOnce({ status: "granted", granted: true, canAskAgain: true });
    const a = createExpoLocationAdapter(mockLoc);
    await expect(a.requestForegroundPermission()).resolves.toBe(true);
    mockLoc.getForegroundPermissionsAsync.mockResolvedValueOnce({ status: "denied", granted: false, canAskAgain: false });
    await expect(a.requestForegroundPermission()).resolves.toBe(false);
    expect(a.lastPermission()).toBe("blocked");
    expect(mockLoc.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  });
  it("reports denied when the user declines", async () => {
    mockLoc.requestForegroundPermissionsAsync.mockResolvedValueOnce({ status: "denied", granted: false, canAskAgain: true });
    const a = createExpoLocationAdapter(mockLoc);
    await expect(a.requestForegroundPermission()).resolves.toBe(false);
    expect(a.lastPermission()).toBe("denied");
  });
  it("rejects contradictory granted permission fields", async () => {
    const a = createExpoLocationAdapter(mockLoc);
    mockLoc.getForegroundPermissionsAsync.mockResolvedValueOnce({
      status: "granted", granted: false, canAskAgain: false,
    });
    await expect(a.requestForegroundPermission()).resolves.toBe(false);
    expect(a.lastPermission()).toBe("blocked");
    expect(mockLoc.watchPositionAsync).not.toHaveBeenCalled();
    mockLoc.getForegroundPermissionsAsync.mockResolvedValueOnce({
      status: "denied", granted: true, canAskAgain: false,
    });
    await expect(a.requestForegroundPermission()).resolves.toBe(false);
    expect(a.lastPermission()).toBe("blocked");
  });
  it("fails closed when location services are off", async () => {
    mockLoc.hasServicesEnabledAsync.mockResolvedValueOnce(false);
    const a = createExpoLocationAdapter(mockLoc);
    await expect(a.watchPosition(jest.fn(), jest.fn())).rejects.toMatchObject({ code: "SERVICES_DISABLED" });
    expect(mockLoc.watchPositionAsync).not.toHaveBeenCalled();
  });
  it("watches with high accuracy and rejects OS-flagged mocks", async () => {
    const onFix = jest.fn(), onError = jest.fn();
    await createExpoLocationAdapter(mockLoc, { timeIntervalMs: 2000 }).watchPosition(onFix, onError);
    expect(mockLoc.watchPositionAsync.mock.calls[0][0]).toMatchObject({ accuracy: 4, timeInterval: 2000 });
    mockLoc.cb!(loc({ mocked: true }));
    expect(onFix).not.toHaveBeenCalled();
    expect(onError.mock.calls[0][0]).toBeInstanceOf(FrontierLocationError);
    mockLoc.cb!(loc());
    expect(onFix).toHaveBeenCalledTimes(1);
    mockLoc.err!("E_LOCATION_UNAVAILABLE");
    expect(onError.mock.calls[1][0].code).toBe("WATCH_FAILED");
  });
  it("wraps watch start failures and validates its sampling policy", async () => {
    mockLoc.watchPositionAsync.mockRejectedValueOnce(new Error("boom"));
    await expect(createExpoLocationAdapter(mockLoc).watchPosition(jest.fn(), jest.fn())).rejects.toMatchObject({ code: "WATCH_FAILED" });
    expect(() => createExpoLocationAdapter(mockLoc, { timeIntervalMs: 5 })).toThrow(FrontierLocationError);
  });
});

describe("FrontierLocationProvider", () => {
  let api: FrontierLocationApi;
  const Probe = () => { api = useFrontierLocation(); return null; };
  const mounted: TestRenderer.ReactTestRenderer[] = [];
  afterEach(() => { act(() => { mounted.splice(0).forEach(m => { try { m.unmount(); } catch { /* already */ } }); }); });
  const mount = (props: Record<string, unknown> = {}) => {
    let r!: TestRenderer.ReactTestRenderer;
    act(() => { r = TestRenderer.create(<FrontierLocationProvider {...props}><Probe /></FrontierLocationProvider>); });
    mounted.push(r);
    return r;
  };

  it("starts idle and never prompts on mount", () => {
    mount();
    expect(api.status).toBe("idle");
    expect(mockLoc.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  });
  it("acquires fixes after a user start and stops cleanly", async () => {
    mount();
    await act(async () => { await api.start(); });
    expect(api.status).toBe("watching");
    act(() => mockLoc.cb!(loc()));
    expect(api.fix).toMatchObject({ latitude_deg: 59.91, sequence: 1 });
    act(() => api.stop());
    expect(api.status).toBe("idle");
    expect(api.fix).toBeNull(); // coordinates must not persist after Stop
    expect(mockLoc.remove).toHaveBeenCalledTimes(1);
  });
  it("keeps watching but surfaces an error for an inaccurate fix", async () => {
    mount();
    await act(async () => { await api.start(); });
    act(() => mockLoc.cb!(loc({ accuracy: 500 })));
    expect(api.status).toBe("watching");
    expect(api.fix).toBeNull();
    expect(api.error?.code).toBe("INVALID_FIX");
  });
  it("shows denied and blocked states", async () => {
    mockLoc.requestForegroundPermissionsAsync.mockResolvedValueOnce({ status: "denied", granted: false, canAskAgain: true });
    mount();
    await act(async () => { await api.start(); });
    expect(api.status).toBe("denied");
    expect(api.error?.code).toBe("PERMISSION_DENIED");
    mockLoc.getForegroundPermissionsAsync.mockResolvedValueOnce({ status: "denied", granted: false, canAskAgain: false });
    await act(async () => { await api.start(); });
    expect(api.status).toBe("blocked");
    expect(mockLoc.watchPositionAsync).not.toHaveBeenCalled();
  });
  it("does not open overlapping native location subscriptions", async () => {
    let release!: (watch: { remove: () => void }) => void;
    mockLoc.watchPositionAsync.mockImplementationOnce(
      () => new Promise(resolve => { release = resolve; }),
    );
    mount();
    const first = api.start();
    const duplicate = api.start();
    await act(async () => { await duplicate; });
    expect(mockLoc.watchPositionAsync).toHaveBeenCalledTimes(1);
    await act(async () => {
      release({ remove: mockLoc.remove });
      await first;
    });
    expect(api.status).toBe("watching");
    act(() => api.stop());
    expect(mockLoc.remove).toHaveBeenCalledTimes(1);
  });
  it("shows an error when services are disabled", async () => {
    mockLoc.hasServicesEnabledAsync.mockResolvedValueOnce(false);
    mount();
    await act(async () => { await api.start(); });
    expect(api).toMatchObject({ status: "error", error: { code: "SERVICES_DISABLED" } });
  });
  it("ends the watch on a native watch failure", async () => {
    mount();
    await act(async () => { await api.start(); });
    act(() => mockLoc.cb!(loc()));
    expect(api.fix).not.toBeNull();
    act(() => mockLoc.err!("revoked"));
    expect(api.status).toBe("error");
    expect(api.fix).toBeNull();
    expect(mockLoc.remove).toHaveBeenCalled();
  });
  it("stops when the app leaves the foreground", async () => {
    mount();
    await act(async () => { await api.start(); });
    act(() => mockLoc.cb!(loc()));
    expect(api.fix).not.toBeNull();
    act(() => mockAppStateListeners.forEach(l => l("background")));
    expect(api.status).toBe("idle");
    expect(api.fix).toBeNull();
    expect(mockLoc.remove).toHaveBeenCalledTimes(1);
  });
  it("reports unavailable when no native adapter exists", async () => {
    mount({ adapter: null });
    await act(async () => { await api.start(); });
    expect(api.status).toBe("unavailable");
  });
  it("releases the watch on unmount", async () => {
    const r = mount();
    await act(async () => { await api.start(); });
    act(() => r.unmount());
    expect(mockLoc.remove).toHaveBeenCalledTimes(1);
  });
  it("throws outside the provider", () => {
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    expect(() => act(() => { TestRenderer.create(<Probe />); })).toThrow(/inside <FrontierLocationProvider>/);
    spy.mockRestore();
  });
});
