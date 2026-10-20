/**
 * Durable, account-scoped camera outbox.
 *
 * A shutter press is acknowledged only after its photo has been copied into
 * document storage AND the manifest is written. Uploads are best-effort and
 * resume on foreground entry; iOS may suspend network work when app closes.
 */
import * as FileSystem from "expo-file-system";
import { api, uploadImage } from "./api";
import { getStoredItem } from "./storage";

export type CaptureMode = "receipt" | "full";
export type LocalCapture = {
  token: string;
  userId: string;
  vehicleId: string;
  mode: CaptureMode;
  createdAt: number;
  completed: boolean;
  receiptFile: string;
  odometerFile?: string;
  receiptMediaId?: string;
  receiptId?: string;
  odometerMediaId?: string;
  odometerReadingId?: string;
  serverId?: string;
  odometerAttached?: boolean;
  lastError?: string;
  retryCount?: number;
  nextRetryAt?: number;
};

const root = `${FileSystem.documentDirectory ?? ""}autoroa-captures/`;
let currentSync: Promise<void> | null = null;

export type PendingCapture = {
  token: string;
  createdAt: number;
  mode: CaptureMode;
  waitingForOdometer: boolean;
  lastError?: string;
  nextRetryAt?: number;
  retryCount: number;
};
export type CaptureOutboxStatus = { items: PendingCapture[]; unreadableCount: number };

export function uploadRetryDelayMs(failureCount: number) {
  return Math.min(15_000 * 2 ** Math.max(0, failureCount - 1), 15 * 60_000);
}

function fileDir(token: string) {
  return `${root}${token}/`;
}

type SavedCapture = LocalCapture & { revision: number };
const writeLocks = new Map<string, Promise<void>>();

async function read(token: string): Promise<SavedCapture> {
  const versions: SavedCapture[] = [];
  for (const slot of ["a", "b"]) {
    try {
      const value = JSON.parse(await FileSystem.readAsStringAsync(
        `${fileDir(token)}manifest.${slot}.json`,
      )) as SavedCapture;
      if (value.token === token && Number.isInteger(value.revision)) versions.push(value);
    } catch {
      // A crash can leave one slot incomplete; the other slot remains valid.
    }
  }
  if (!versions.length) throw new Error("No recoverable capture manifest");
  return versions.sort((a, b) => b.revision - a.revision)[0];
}

async function write(entry: LocalCapture) {
  const priorWrite = writeLocks.get(entry.token) ?? Promise.resolve();
  const operation = priorWrite.catch(() => {}).then(async () => {
    const directory = fileDir(entry.token);
    await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
    let previous: SavedCapture | undefined;
    try { previous = await read(entry.token); } catch { /* new entry */ }
    const merged: SavedCapture = {
      ...previous, ...entry,
      receiptMediaId: entry.receiptMediaId ?? previous?.receiptMediaId,
      receiptId: entry.receiptId ?? previous?.receiptId,
      odometerReadingId: entry.odometerReadingId ?? previous?.odometerReadingId,
      odometerFile: entry.odometerFile ?? previous?.odometerFile,
      odometerMediaId: entry.odometerMediaId ?? previous?.odometerMediaId,
      serverId: entry.serverId ?? previous?.serverId,
      odometerAttached: entry.odometerAttached ?? previous?.odometerAttached,
      completed: entry.completed || previous?.completed || false,
      revision: (previous?.revision ?? 0) + 1,
    };
    const slot = merged.revision % 2 ? "a" : "b";
    await FileSystem.writeAsStringAsync(
      `${directory}manifest.${slot}.json`, JSON.stringify(merged),
    );
  });
  writeLocks.set(entry.token, operation);
  try { await operation; } finally {
    if (writeLocks.get(entry.token) === operation) writeLocks.delete(entry.token);
  }
}

function createToken() {
  // An idempotency identifier, not a security credential.
  return `cap_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;
}

export async function saveReceiptLocally(uri: string, vehicleId: string, mode: CaptureMode) {
  if (!FileSystem.documentDirectory) throw new Error("Private local storage is unavailable");
  const userId = await getStoredItem("autoroa_user_id");
  if (!userId) throw new Error("Sign in before capturing a receipt");
  const token = createToken();
  const directory = fileDir(token);
  await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
  const receiptFile = `${directory}receipt.jpg`;
  await FileSystem.copyAsync({ from: uri, to: receiptFile });
  const entry: LocalCapture = {
    token, userId, vehicleId, mode, createdAt: Date.now(),
    completed: mode === "receipt", receiptFile,
  };
  await write(entry);
  return token;
}

export async function saveOdometerLocally(token: string, uri: string) {
  const entry = await read(token);
  if (entry.odometerFile) throw new Error("This capture already contains an odometer");
  const odometerFile = `${fileDir(token)}odometer.jpg`;
  await FileSystem.copyAsync({ from: uri, to: odometerFile });
  entry.odometerFile = odometerFile;
  entry.completed = true;
  await write(entry);
}

export async function finishReceiptOnly(token: string) {
  const entry = await read(token);
  entry.completed = true;
  await write(entry);
}

async function syncOne(entry: LocalCapture) {
  if (!entry.receiptMediaId) {
    entry.receiptMediaId = (await uploadImage(entry.receiptFile, "RECEIPT")).id;
    await write(entry);
  }
  if (!entry.serverId) {
    const request = entry.receiptId
      ? { client_key: entry.token, vehicle_id: entry.vehicleId, receipt_id: entry.receiptId }
      : { client_token: entry.token, vehicle_id: entry.vehicleId, receipt_media_asset_id: entry.receiptMediaId };
    const response = await api.post<{id:string}>("/quick-captures", request);
    entry.serverId = response.id;
    await write(entry);
  }
  if (entry.odometerFile && !entry.odometerMediaId) {
    entry.odometerMediaId = (await uploadImage(entry.odometerFile, "ODOMETER")).id;
    await write(entry);
  }
  if (entry.odometerMediaId && !entry.odometerAttached) {
    const reading = entry.odometerReadingId
      ? { odometer_reading_id: entry.odometerReadingId }
      : { odometer_media_asset_id: entry.odometerMediaId };
    await api.post(`/quick-captures/${entry.serverId}/odometer`, reading);
    entry.odometerAttached = true;
    await write(entry);
  }
  // The server now owns the durable media and processing job. The local
  // outbox is removable only when both requested photos are acknowledged.
  if (entry.completed && entry.serverId && (!entry.odometerFile || entry.odometerAttached)) {
    await FileSystem.deleteAsync(fileDir(entry.token), { idempotent: true });
  }
}


type LegacyCapture = {
  clientKey: string;
  ownerId: string;
  vehicleId: string;
  mode: CaptureMode;
  receiptPath: string;
  odometerPath?: string;
  receiptReady: boolean;
  odometerReady: boolean;
  receiptMediaId?: string;
  receiptId?: string;
  captureId?: string;
  odometerMediaId?: string;
  odometerReadingId?: string;
  odometerAttached?: boolean;
};

/**
 * Import the previously released manifest format before attempting to sync.
 * Old source photos are removed only after both new manifest slots and their
 * private photo copies have been written successfully.
 */
async function migrateLegacyOutbox(activeUser: string) {
  if (!FileSystem.documentDirectory) return;
  const oldRoot = `${FileSystem.documentDirectory}quick-captures/`;
  const info = await FileSystem.getInfoAsync(oldRoot);
  if (!info.exists) return;
  const filenames = await FileSystem.readDirectoryAsync(oldRoot);
  const tokens = [...new Set(filenames.filter(name => /\.json(?:\.tmp)?$/.test(name))
    .map(name => name.replace(/\.json(?:\.tmp)?$/, "")))];
  for (const token of tokens) {
    if (!/^[A-Za-z0-9_-]{8,80}$/.test(token)) continue;
    try {
      let previous: LegacyCapture | undefined;
      for (const suffix of [".json.tmp", ".json"]) {
        try {
          const candidate = JSON.parse(await FileSystem.readAsStringAsync(`${oldRoot}${token}${suffix}`)) as LegacyCapture;
          if (candidate.clientKey === token && candidate.ownerId === activeUser && candidate.receiptReady) {
            previous = candidate;
            break;
          }
        } catch {
          // If an interrupted write damaged a slot, inspect the other slot.
        }
      }
      if (!previous) continue;
      let imported: SavedCapture | undefined;
      try { imported = await read(token); } catch { /* not imported yet */ }
      if (!imported) {
        const directory = fileDir(token);
        await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
        const receiptFile = `${directory}receipt.jpg`;
        await FileSystem.copyAsync({ from: previous.receiptPath, to: receiptFile });
        const receiptInfo = await FileSystem.getInfoAsync(receiptFile);
        if (!receiptInfo.exists || receiptInfo.size === 0) throw new Error("Receipt copy is incomplete");
        let odometerFile: string | undefined;
        if (previous.odometerReady && previous.odometerPath) {
          odometerFile = `${directory}odometer.jpg`;
          await FileSystem.copyAsync({ from: previous.odometerPath, to: odometerFile });
          const odoInfo = await FileSystem.getInfoAsync(odometerFile);
          if (!odoInfo.exists || odoInfo.size === 0) throw new Error("Odometer copy is incomplete");
        }
        const entry: LocalCapture = {
          token, userId: activeUser, vehicleId: previous.vehicleId, mode: previous.mode,
          createdAt: Date.now() - 6 * 60_000,
          completed: previous.mode === "receipt" || Boolean(odometerFile),
          receiptFile, odometerFile,
          receiptMediaId: previous.receiptMediaId,
          receiptId: previous.receiptId,
          serverId: previous.captureId,
          odometerMediaId: previous.odometerMediaId,
          odometerReadingId: previous.odometerReadingId,
          odometerAttached: previous.odometerAttached,
        };
        await write(entry);
        await write(entry);
        imported = await read(token);
      }
      if (!imported || imported.userId !== activeUser) continue;
      await FileSystem.deleteAsync(`${oldRoot}${token}.json`, { idempotent: true });
      await FileSystem.deleteAsync(`${oldRoot}${token}.json.tmp`, { idempotent: true });
      await FileSystem.deleteAsync(previous.receiptPath, { idempotent: true });
      if (previous.odometerReady && previous.odometerPath) {
        await FileSystem.deleteAsync(previous.odometerPath, { idempotent: true });
      }
    } catch {
      // On any failure preserve the original manifest and photos for another try.
    }
  }
}

/** Return only the currently signed-in account's unsent photos. */
export async function getPendingCaptures(): Promise<CaptureOutboxStatus> {
  if (!FileSystem.documentDirectory) return { items: [], unreadableCount: 0 };
  const activeUser = await getStoredItem("autoroa_user_id");
  if (!activeUser) return { items: [], unreadableCount: 0 };
  await migrateLegacyOutbox(activeUser);
  const directory = await FileSystem.getInfoAsync(root);
  if (!directory.exists) return { items: [], unreadableCount: 0 };
  const tokens = await FileSystem.readDirectoryAsync(root);
  const items: PendingCapture[] = [];
  let unreadableCount = 0;
  for (const token of tokens) {
    try {
      const entry = await read(token);
      if (entry.userId !== activeUser) continue;
      items.push({
        token: entry.token,
        createdAt: entry.createdAt,
        mode: entry.mode,
        waitingForOdometer: entry.mode === "full" && !entry.completed &&
          Date.now() - entry.createdAt < 5 * 60_000,
        lastError: entry.lastError,
        nextRetryAt: entry.nextRetryAt,
        retryCount: entry.retryCount ?? 0,
      });
    } catch {
      // A damaged manifest is NOT deleted; tell the user something needs attention.
      unreadableCount += 1;
    }
  }
  return { items: items.sort((a, b) => b.createdAt - a.createdAt), unreadableCount };
}

async function performSync(force: boolean) {
  if (!FileSystem.documentDirectory) return;
  const activeUser = await getStoredItem("autoroa_user_id");
  if (!activeUser) return;
  await migrateLegacyOutbox(activeUser);
  const directory = await FileSystem.getInfoAsync(root);
  if (!directory.exists) return;
  const tokens = await FileSystem.readDirectoryAsync(root);
  for (const token of tokens) {
    try {
      const entry = await read(token);
      if (entry.userId !== activeUser) continue;
      if (!force && entry.nextRetryAt && Date.now() < entry.nextRetryAt) continue;
      // A full scan abandoned after its first photo remains a valid fuel receipt.
      if (!entry.completed && Date.now() - entry.createdAt > 5 * 60_000) {
        entry.completed = true;
        await write(entry);
      }
      await syncOne(entry);
    } catch (error) {
      try {
        const entry = await read(token);
        if (entry.userId !== activeUser) continue;
        const failureCount = (entry.retryCount ?? 0) + 1;
        entry.retryCount = failureCount;
        entry.nextRetryAt = Date.now() + uploadRetryDelayMs(failureCount);
        entry.lastError = error instanceof Error ? error.message : "Sync failed";
        await write(entry);
      } catch {
        // Never delete photos with an unreadable manifest.
      }
    }
  }
}

/**
 * Only one sync may run at a time. A Retry tap waits for the current operation.
 * iOS cannot guarantee continued JavaScript execution after force-quit.
 */
export function syncQuickCaptures(options: {force?: boolean} = {}): Promise<void> {
  if (currentSync) return currentSync;
  currentSync = performSync(options.force ?? false).finally(() => { currentSync = null; });
  return currentSync;
}
