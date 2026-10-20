import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  files: new Map<string, string>(),
  dirs: new Set<string>(["file:///docs/"]),
  owner: "user-one",
  post: vi.fn(),
  upload: vi.fn(),
}));

vi.mock("expo-file-system", () => ({
  documentDirectory: "file:///docs/",
  getInfoAsync: vi.fn(async (path: string) => {
    const data = state.files.get(path);
    return data !== undefined
      ? { exists: true, isDirectory: false, size: data.length, uri: path }
      : state.dirs.has(path)
        ? { exists: true, isDirectory: true, uri: path }
        : { exists: false, isDirectory: false, uri: path };
  }),
  makeDirectoryAsync: vi.fn(async (path: string) => {
    // Expo's intermediates option creates each parent directory as well.
    let current = "file:///docs/";
    for (const segment of path.slice(current.length).split("/").filter(Boolean)) {
      current += `${segment}/`;
      state.dirs.add(current);
    }
  }),
  readAsStringAsync: vi.fn(async (path: string) => {
    const value = state.files.get(path);
    if (value === undefined) throw new Error("File not found");
    return value;
  }),
  writeAsStringAsync: vi.fn(async (path: string, data: string) => {
    state.files.set(path, data);
  }),
  copyAsync: vi.fn(async ({ from, to }: { from: string; to: string }) => {
    const value = state.files.get(from);
    if (value === undefined) throw new Error("Source photo missing");
    state.files.set(to, value);
  }),
  readDirectoryAsync: vi.fn(async (path: string) => {
    const names = [...state.files.keys(), ...state.dirs]
      .filter(item => item.startsWith(path) && item !== path)
      .map(item => item.slice(path.length).split("/")[0])
      .filter(Boolean);
    return [...new Set(names)];
  }),
  deleteAsync: vi.fn(async (path: string) => {
    for (const key of [...state.files.keys()]) {
      if (key === path || key.startsWith(path)) state.files.delete(key);
    }
    for (const key of [...state.dirs]) {
      if (key === path || key.startsWith(path)) state.dirs.delete(key);
    }
  }),
}));

vi.mock("./storage", () => ({
  getStoredItem: vi.fn(async (key: string) => key === "autoroa_user_id" ? state.owner : null),
}));
vi.mock("./api", () => ({
  api: { post: state.post },
  uploadImage: state.upload,
}));

import { getPendingCaptures, syncQuickCaptures, uploadRetryDelayMs } from "./capture-queue";

const oldRoot = "file:///docs/quick-captures/";
function legacy(token: string, extras: Record<string, unknown> = {}) {
  const receiptPath = `${oldRoot}${token}-receipt.jpg`;
  state.dirs.add(oldRoot);
  state.files.set(receiptPath, "photograph-original-bytes");
  state.files.set(`${oldRoot}${token}.json`, JSON.stringify({
    clientKey: token, ownerId: "user-one", vehicleId: "vehicle-one",
    mode: "receipt", receiptPath,
    odometerPath: `${oldRoot}${token}-odometer.jpg`,
    receiptReady: true, odometerReady: false,
    status: "QUEUED", ...extras,
  }));
  return receiptPath;
}

beforeEach(() => {
  state.files.clear();
  state.dirs.clear();
  state.dirs.add("file:///docs/");
  state.owner = "user-one";
  state.post.mockReset().mockResolvedValue({ id: "server-capture" });
  state.upload.mockReset().mockResolvedValue({ id: "new-media" });
});

describe("Quick Capture legacy photo recovery", () => {
  it("imports old receipts without re-creating their existing OCR receipt", async () => {
    const token = "capture-previous-001";
    const oldPhoto = legacy(token, { receiptMediaId: "media-old", receiptId: "receipt-old" });
    await syncQuickCaptures();
    expect(state.post).toHaveBeenCalledWith("/quick-captures", {
      client_key: token, vehicle_id: "vehicle-one", receipt_id: "receipt-old",
    });
    expect(state.upload).not.toHaveBeenCalled();
    expect(state.files.has(oldPhoto)).toBe(false);
    expect(state.files.has(`${oldRoot}${token}.json`)).toBe(false);
    expect(state.files.has(`file:///docs/autoroa-captures/${token}/receipt.jpg`)).toBe(false);
  });

  it("preserves the copied photo and retries when the network fails", async () => {
    const token = "capture-retry-002";
    const oldPhoto = legacy(token);
    state.post.mockRejectedValueOnce(new Error("Connection lost"));
    await syncQuickCaptures();
    expect(state.files.has(oldPhoto)).toBe(false);
    expect(state.files.has(`file:///docs/autoroa-captures/${token}/receipt.jpg`)).toBe(true);
    expect(state.files.has(`file:///docs/autoroa-captures/${token}/manifest.a.json`)).toBe(true);
    expect(state.files.has(`file:///docs/autoroa-captures/${token}/manifest.b.json`)).toBe(true);
    const waiting = await getPendingCaptures();
    expect(waiting.items).toHaveLength(1);
    expect(waiting.items[0].retryCount).toBe(1);
    expect(waiting.items[0].lastError).toContain("Connection lost");
    expect(waiting.items[0].nextRetryAt).toBeGreaterThan(Date.now());
    await syncQuickCaptures();
    expect(state.post).toHaveBeenCalledTimes(1);
    await syncQuickCaptures({force:true});
    expect(state.post).toHaveBeenCalledTimes(2);
    expect(state.files.has(`file:///docs/autoroa-captures/${token}/receipt.jpg`)).toBe(false);
  });

  it("keeps old photos owned by another account untouched", async () => {
    const token = "capture-other-owner";
    const oldPhoto = legacy(token, { ownerId: "another-user" });
    await syncQuickCaptures();
    expect(state.files.has(oldPhoto)).toBe(true);
    expect(state.files.has(`${oldRoot}${token}.json`)).toBe(true);
    expect(state.post).not.toHaveBeenCalled();
  });

  it("reuses an existing odometer reading after importing a two-photo capture", async () => {
    const token = "capture-full-003";
    const odo = `${oldRoot}${token}-odometer.jpg`;
    legacy(token, {
      mode: "full", odometerReady: true,
      receiptMediaId: "media-1", receiptId: "receipt-1",
      odometerMediaId: "media-odo", odometerReadingId: "reading-1",
    });
    state.files.set(odo, "odometer-photograph");
    await syncQuickCaptures();
    expect(state.post).toHaveBeenCalledWith("/quick-captures/server-capture/odometer", {
      odometer_reading_id: "reading-1",
    });
    expect(state.upload).not.toHaveBeenCalled();
    expect(state.files.has(odo)).toBe(false);
  });

  it("does not delete legacy pictures when an import copy fails", async () => {
    const token = "capture-broken-004";
    const oldPhoto = legacy(token);
    state.files.delete(oldPhoto);
    await syncQuickCaptures();
    expect(state.files.has(`${oldRoot}${token}.json`)).toBe(true);
    expect(state.post).not.toHaveBeenCalled();
  });
});

describe("Capture outbox retries and account privacy", () => {
  it("uses bounded increasing delay so the app does not hammer the network", () => {
    expect(uploadRetryDelayMs(1)).toBe(15_000);
    expect(uploadRetryDelayMs(2)).toBe(30_000);
    expect(uploadRetryDelayMs(3)).toBe(60_000);
    expect(uploadRetryDelayMs(200)).toBe(900_000);
  });
  it("does not show another account's saved photos", async () => {
    legacy("capture-owner-outside", {ownerId:"another-user"});
    const queue = await getPendingCaptures();
    expect(queue.items).toHaveLength(0);
    expect(queue.unreadableCount).toBe(0);
  });
  it("surfaces unreadable capture manifests without deleting any photo", async () => {
    const directory = "file:///docs/autoroa-captures/bad-manifest/";
    state.dirs.add("file:///docs/autoroa-captures/");
    state.dirs.add(directory);
    state.files.set(directory + "receipt.jpg", "do not lose me");
    state.files.set(directory + "manifest.a.json", "{broken");
    const queue = await getPendingCaptures();
    expect(queue.items).toHaveLength(0);
    expect(queue.unreadableCount).toBe(1);
    expect(state.files.get(directory + "receipt.jpg")).toBe("do not lose me");
  });
});
