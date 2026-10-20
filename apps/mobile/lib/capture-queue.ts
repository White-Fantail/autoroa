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
  odometerMediaId?: string;
  serverId?: string;
  odometerAttached?: boolean;
  lastError?: string;
};

const root = `${FileSystem.documentDirectory ?? ""}autoroa-captures/`;
let syncing = false;

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
    const response = await api.post<{id:string}>("/quick-captures", {
      client_token: entry.token,
      vehicle_id: entry.vehicleId,
      receipt_media_asset_id: entry.receiptMediaId,
    });
    entry.serverId = response.id;
    await write(entry);
  }
  if (entry.odometerFile && !entry.odometerMediaId) {
    entry.odometerMediaId = (await uploadImage(entry.odometerFile, "ODOMETER")).id;
    await write(entry);
  }
  if (entry.odometerMediaId && !entry.odometerAttached) {
    await api.post(`/quick-captures/${entry.serverId}/odometer`, {
      odometer_media_asset_id: entry.odometerMediaId,
    });
    entry.odometerAttached = true;
    await write(entry);
  }
  // The server now owns the durable media and processing job. The local
  // outbox is removable only when both requested photos are acknowledged.
  if (entry.completed && entry.serverId && (!entry.odometerFile || entry.odometerAttached)) {
    await FileSystem.deleteAsync(fileDir(entry.token), { idempotent: true });
  }
}

export async function syncQuickCaptures() {
  if (syncing || !FileSystem.documentDirectory) return;
  syncing = true;
  try {
    const activeUser = await getStoredItem("autoroa_user_id");
    if (!activeUser) return;
    const directory = await FileSystem.getInfoAsync(root);
    if (!directory.exists) return;
    const tokens = await FileSystem.readDirectoryAsync(root);
    for (const token of tokens) {
      try {
        const entry = await read(token);
        if (entry.userId !== activeUser) continue;
        // If the user left midway through Full Scan, retain the receipt and
        // gracefully downgrade to receipt-only after five minutes.
        if (!entry.completed && Date.now() - entry.createdAt > 5 * 60_000) {
          entry.completed = true;
          await write(entry);
        }
        await syncOne(entry);
      } catch (error) {
        try {
          const entry = await read(token);
          entry.lastError = error instanceof Error ? error.message : "Sync failed";
          await write(entry);
        } catch {
          // Keep damaged manifests for recovery; never discard local photos.
        }
      }
    }
  } finally {
    syncing = false;
  }
}
