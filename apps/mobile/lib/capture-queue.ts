import * as FileSystem from "expo-file-system";
import { Platform } from "react-native";
import { api, uploadImage } from "./api";
import { getStoredItem } from "./storage";

export type CaptureMode = "receipt" | "full";
export type LocalCapture = {
  clientKey: string;
  ownerId: string;
  vehicleId: string;
  mode: CaptureMode;
  receiptPath: string;
  odometerPath: string;
  receiptReady: boolean;
  odometerReady: boolean;
  receiptMediaId?: string;
  receiptId?: string;
  receiptJobId?: string;
  captureId?: string;
  odometerMediaId?: string;
  odometerReadingId?: string;
  odometerJobId?: string;
  odometerAttached?: boolean;
  status: "CAPTURING" | "QUEUED" | "SYNCING" | "UPLOADED" | "RETRY";
  lastError?: string;
};

const root = FileSystem.documentDirectory ? `${FileSystem.documentDirectory}quick-captures/` : null;
const pathFor = (key: string) => `${root}${key}.json`;
const draftFor = (key: string) => `${root}${key}.json.tmp`;
let currentSync: Promise<void> | undefined;
const fileLocks = new Map<string, Promise<unknown>>();

async function ensureDirectory() {
  if (Platform.OS === "web" || !root) throw new Error("Quick Capture requires the installed mobile app.");
  await FileSystem.makeDirectoryAsync(root, { intermediates: true });
}

async function readRecord(key: string): Promise<LocalCapture | null> {
  await ensureDirectory();
  const temporary = draftFor(key);
  for (const path of [temporary, pathFor(key)]) {
    const info = await FileSystem.getInfoAsync(path);
    if (!info.exists) continue;
    try {
      const value = JSON.parse(await FileSystem.readAsStringAsync(path)) as LocalCapture;
      if (value.clientKey === key) return value;
    } catch {
      // Retain incomplete files for recovery rather than discarding captured photos.
    }
  }
  return null;
}

async function saveRecord(record: LocalCapture) {
  await ensureDirectory();
  const path = pathFor(record.clientKey);
  const draft = draftFor(record.clientKey);
  await FileSystem.writeAsStringAsync(draft, JSON.stringify(record));
  await FileSystem.deleteAsync(path, { idempotent: true });
  await FileSystem.moveAsync({ from: draft, to: path });
}

async function changeRecord(key: string, change: (record: LocalCapture) => LocalCapture): Promise<LocalCapture> {
  const previous = fileLocks.get(key) ?? Promise.resolve();
  const task = previous.catch(() => undefined).then(async () => {
    const record = await readRecord(key);
    if (!record) throw new Error("Capture was not found.");
    const updated = change(record);
    await saveRecord(updated);
    return updated;
  });
  fileLocks.set(key, task);
  try { return await task; }
  finally { if (fileLocks.get(key) === task) fileLocks.delete(key); }
}

export async function createLocalCapture(vehicleId: string, mode: CaptureMode) {
  await ensureDirectory();
  const ownerId = await getStoredItem("autoroa_user_id");
  if (!ownerId) throw new Error("Sign in before capturing a receipt.");
  const key = `capture-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  const record: LocalCapture = {
    clientKey: key, ownerId, vehicleId, mode,
    receiptPath: `${root}${key}-receipt.jpg`,
    odometerPath: `${root}${key}-odometer.jpg`,
    receiptReady: false, odometerReady: false, status: "CAPTURING"
  };
  await saveRecord(record);
  return record;
}

export async function saveCapturePhoto(key: string, kind: "receipt" | "odometer", sourceUri: string) {
  const record = await readRecord(key);
  if (!record) throw new Error("Capture was not found.");
  if (kind === "odometer" && !record.receiptReady) throw new Error("Capture the receipt first.");
  const path = kind === "receipt" ? record.receiptPath : record.odometerPath;
  await FileSystem.copyAsync({ from: sourceUri, to: path });
  const info = await FileSystem.getInfoAsync(path);
  if (!info.exists || (typeof info.size === "number" && info.size === 0)) throw new Error("Photo could not be stored safely.");
  return changeRecord(key, value => ({
    ...value,
    ...(kind === "receipt" ? { receiptReady: true } : { odometerReady: true }),
    status: "QUEUED",
    lastError: undefined
  }));
}

export async function localCaptureList() {
  await ensureDirectory();
  const names = await FileSystem.readDirectoryAsync(root!);
  const keys = [...new Set(names.filter(name => name.endsWith(".json") || name.endsWith(".json.tmp"))
    .map(name => name.replace(/\.json(?:\.tmp)?$/, "")))];
  const entries = await Promise.all(keys.map(readRecord));
  return entries.filter((item): item is LocalCapture => item != null);
}

async function syncEntry(record: LocalCapture) {
  if (!record.receiptReady || record.status === "UPLOADED" && (!record.odometerReady || record.odometerAttached)) return;
  const key = record.clientKey;
  const save = (patch: Partial<LocalCapture>) =>
    changeRecord(key, entry => ({ ...entry, ...patch, lastError: undefined }));
  await save({ status: "SYNCING" });
  try {
    let entry = (await readRecord(key))!;
    if (!entry.receiptMediaId) {
      const uploaded = await uploadImage(entry.receiptPath, "RECEIPT");
      entry = await save({ receiptMediaId: uploaded.id });
    }
    if (!entry.receiptId) {
      const receipt = await api.post<{id: string}>("/receipts", { media_asset_id: entry.receiptMediaId });
      entry = await save({ receiptId: receipt.id });
    }
    if (!entry.receiptJobId) {
      const job = await api.post<{id: string}>("/ocr-jobs", { kind: "RECEIPT", resource_id: entry.receiptId });
      entry = await save({ receiptJobId: job.id });
    }
    if (!entry.captureId) {
      const capture = await api.post<{id: string}>("/quick-captures", {
        client_key: key, vehicle_id: entry.vehicleId, receipt_id: entry.receiptId, full_tank: false
      });
      entry = await save({ captureId: capture.id });
    }
    if (entry.odometerReady && !entry.odometerAttached) {
      if (!entry.odometerMediaId) {
        const uploaded = await uploadImage(entry.odometerPath, "ODOMETER");
        entry = await save({ odometerMediaId: uploaded.id });
      }
      if (!entry.odometerReadingId) {
        const reading = await api.post<{id: string}>("/odometer-readings", {
          media_asset_id: entry.odometerMediaId, vehicle_id: entry.vehicleId
        });
        entry = await save({ odometerReadingId: reading.id });
      }
      if (!entry.odometerJobId) {
        const job = await api.post<{id: string}>("/ocr-jobs", {
          kind: "ODOMETER", resource_id: entry.odometerReadingId
        });
        entry = await save({ odometerJobId: job.id });
      }
      await api.post(`/quick-captures/${entry.captureId}/odometer`, {
        odometer_reading_id: entry.odometerReadingId
      });
      entry = await save({ odometerAttached: true });
    }
    await save({ status: "UPLOADED" });
  } catch (error) {
    await changeRecord(key, entry => ({
      ...entry, status: "RETRY", lastError: error instanceof Error ? error.message : "Upload interrupted."
    }));
  }
}

async function syncAll() {
  const ownerId = await getStoredItem("autoroa_user_id");
  if (!ownerId) return;
  for (const entry of await localCaptureList()) {
    if (entry.ownerId === ownerId && entry.receiptReady) await syncEntry(entry);
  }
}

export function syncLocalCaptures() {
  if (!currentSync) {
    currentSync = syncAll().finally(() => { currentSync = undefined; });
  }
  return currentSync;
}
