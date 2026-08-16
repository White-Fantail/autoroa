"use client";

import { useEffect, useState } from "react";

const supportedMimeTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const inferredMimeByExtension: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  heic: "image/heic",
  heif: "image/heif",
};

const UPLOAD_TIMEOUT_MS = 45_000;
const API_STAGE_TIMEOUT_MS = 30_000;
type PhotoGps = { latitude: number; longitude: number };

export function inferImageMime(file: File) {
  const declared = file.type.trim().toLowerCase();
  if (declared) return declared;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return inferredMimeByExtension[extension] ?? "";
}

export async function sniffImageMime(file: Blob) {
  const bytes = new Uint8Array(await file.slice(0, 32).arrayBuffer());
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 && bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a) return "image/png";
  if (bytes.length >= 12 && String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP") return "image/webp";
  if (bytes.length >= 12 && String.fromCharCode(...bytes.slice(4, 8)) === "ftyp") {
    const brand = String.fromCharCode(...bytes.slice(8, 12)).toLowerCase();
    if (["heic", "heix", "hevc", "hevx", "heim", "heis", "mif1", "msf1"].includes(brand)) return "image/heic";
  }
  return "";
}

function replaceExtension(name: string, extension: string) {
  const dot = name.lastIndexOf(".");
  return `${dot > 0 ? name.slice(0, dot) : name}.${extension}`;
}

function parseGpsFromTiff(bytes: Uint8Array, tiff: number): PhotoGps | undefined {
  const little = bytes[tiff] === 0x49 && bytes[tiff + 1] === 0x49;
  const big = bytes[tiff] === 0x4d && bytes[tiff + 1] === 0x4d;
  if (!little && !big) return undefined;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const u16 = (offset: number) => view.getUint16(offset, little);
  const u32 = (offset: number) => view.getUint32(offset, little);
  const rational = (offset: number) => { const denominator = u32(offset + 4); return denominator ? u32(offset) / denominator : 0; };
  try {
    if (u16(tiff + 2) !== 42) return undefined;
    const ifd0 = tiff + u32(tiff + 4);
    const count = u16(ifd0);
    let gpsOffset: number | undefined;
    for (let i = 0; i < count; i += 1) {
      const entry = ifd0 + 2 + i * 12;
      if (u16(entry) === 0x8825) { gpsOffset = tiff + u32(entry + 8); break; }
    }
    if (gpsOffset == null) return undefined;
    const gpsCount = u16(gpsOffset);
    let latRef = "", lonRef = "";
    let latValues: number[] | undefined, lonValues: number[] | undefined;
    for (let i = 0; i < gpsCount; i += 1) {
      const entry = gpsOffset + 2 + i * 12;
      const tag = u16(entry), type = u16(entry + 2), itemCount = u32(entry + 4);
      if (tag === 1 && type === 2 && itemCount >= 1) latRef = String.fromCharCode(bytes[entry + 8]).toUpperCase();
      if (tag === 3 && type === 2 && itemCount >= 1) lonRef = String.fromCharCode(bytes[entry + 8]).toUpperCase();
      if ((tag === 2 || tag === 4) && type === 5 && itemCount === 3) {
        const data = tiff + u32(entry + 8);
        const values = [rational(data), rational(data + 8), rational(data + 16)];
        if (tag === 2) latValues = values; else lonValues = values;
      }
    }
    if (!latValues || !lonValues || !/[NS]/.test(latRef) || !/[EW]/.test(lonRef)) return undefined;
    const decimal = ([degrees, minutes, seconds]: number[]) => degrees + minutes / 60 + seconds / 3600;
    const latitude = decimal(latValues) * (latRef === "S" ? -1 : 1);
    const longitude = decimal(lonValues) * (lonRef === "W" ? -1 : 1);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return undefined;
    return { latitude, longitude };
  } catch { return undefined; }
}

export function extractGpsFromImageBytes(buffer: ArrayBuffer): PhotoGps | undefined {
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i + 8 < bytes.length; i += 1) {
    const little = bytes[i] === 0x49 && bytes[i + 1] === 0x49 && bytes[i + 2] === 0x2a && bytes[i + 3] === 0;
    const big = bytes[i] === 0x4d && bytes[i + 1] === 0x4d && bytes[i + 2] === 0 && bytes[i + 3] === 0x2a;
    if (little || big) { const gps = parseGpsFromTiff(bytes, i); if (gps) return gps; }
  }
  return undefined;
}

function writeRational(view: DataView, offset: number, value: number, denominator = 1_000_000) {
  view.setUint32(offset, Math.round(value * denominator), true); view.setUint32(offset + 4, denominator, true);
}

export function gpsExifSegment(gps: PhotoGps): Uint8Array {
  const tiff = new Uint8Array(128); const view = new DataView(tiff.buffer);
  tiff[0] = 0x49; tiff[1] = 0x49; view.setUint16(2, 42, true); view.setUint32(4, 8, true);
  view.setUint16(8, 1, true); view.setUint16(10, 0x8825, true); view.setUint16(12, 4, true); view.setUint32(14, 1, true); view.setUint32(18, 26, true); view.setUint32(22, 0, true);
  view.setUint16(26, 4, true);
  const entry = (index: number, tag: number, type: number, count: number, value: number) => { const offset = 28 + index * 12; view.setUint16(offset, tag, true); view.setUint16(offset + 2, type, true); view.setUint32(offset + 4, count, true); view.setUint32(offset + 8, value, true); };
  const latRef = gps.latitude < 0 ? "S" : "N", lonRef = gps.longitude < 0 ? "W" : "E";
  entry(0, 1, 2, 2, latRef.charCodeAt(0)); entry(1, 2, 5, 3, 80); entry(2, 3, 2, 2, lonRef.charCodeAt(0)); entry(3, 4, 5, 3, 104); view.setUint32(76, 0, true);
  const dms = (coordinate: number) => { const absolute = Math.abs(coordinate), degrees = Math.floor(absolute), minuteValue = (absolute - degrees) * 60, minutes = Math.floor(minuteValue); return [degrees, minutes, (minuteValue - minutes) * 60] as const; };
  const lat = dms(gps.latitude), lon = dms(gps.longitude);
  writeRational(view, 80, lat[0], 1); writeRational(view, 88, lat[1], 1); writeRational(view, 96, lat[2]); writeRational(view, 104, lon[0], 1); writeRational(view, 112, lon[1], 1); writeRational(view, 120, lon[2]);
  const payload = new Uint8Array(6 + tiff.length); payload.set([0x45, 0x78, 0x69, 0x66, 0, 0]); payload.set(tiff, 6);
  const segment = new Uint8Array(payload.length + 4); segment.set([0xff, 0xe1]); const length = payload.length + 2; segment[2] = (length >> 8) & 0xff; segment[3] = length & 0xff; segment.set(payload, 4); return segment;
}

export async function injectGpsIntoJpeg(blob: Blob, gps: PhotoGps | undefined) {
  if (!gps) return blob;
  const bytes = new Uint8Array(await blob.arrayBuffer());
  if (bytes.length < 2 || bytes[0] !== 0xff || bytes[1] !== 0xd8) throw new Error("Converted image is not JPEG data");
  const exif = gpsExifSegment(gps);
  const output = new Uint8Array(bytes.length + exif.length);
  output.set(bytes.subarray(0, 2), 0);
  output.set(exif, 2);
  output.set(bytes.subarray(2), 2 + exif.length);
  return new Blob([output.buffer], { type: "image/jpeg" });
}

async function assertBrowserDecodesJpeg(blob: Blob) {
  if (await sniffImageMime(blob) !== "image/jpeg") throw new Error("Converted image is not JPEG data");
  const objectUrl = URL.createObjectURL(blob);
  try {
    const image = new Image(); image.decoding = "async"; image.src = objectUrl; await image.decode();
    if (!image.naturalWidth || !image.naturalHeight) throw new Error("Converted JPEG has invalid dimensions");
  } finally { URL.revokeObjectURL(objectUrl); }
}

async function transcodeToJpeg(file: File) {
  const gps = extractGpsFromImageBytes(await file.arrayBuffer());
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = new Image(); image.decoding = "async"; image.src = objectUrl;
    try { await image.decode(); } catch (cause) { throw new Error("Safari could not decode this HEIC/HEIF photo for conversion", { cause }); }
    const maximumDimension = 4096; const scale = Math.min(1, maximumDimension / Math.max(image.naturalWidth, image.naturalHeight));
    const width = Math.max(1, Math.round(image.naturalWidth * scale)), height = Math.max(1, Math.round(image.naturalHeight * scale));
    const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height; const context = canvas.getContext("2d"); if (!context) throw new Error("Canvas is unavailable"); context.drawImage(image, 0, 0, width, height);
    const rendered = await new Promise<Blob>((resolve, reject) => canvas.toBlob((result) => result ? resolve(result) : reject(new Error("JPEG conversion failed")), "image/jpeg", 0.9));
    const blob = await injectGpsIntoJpeg(rendered, gps);
    await assertBrowserDecodesJpeg(blob);
    return new File([blob], replaceExtension(file.name || "photo", "jpg"), { type: "image/jpeg", lastModified: file.lastModified });
  } finally { URL.revokeObjectURL(objectUrl); }
}

export async function normalizePickedImage(file: File) {
  const actualMime = await sniffImageMime(file), declaredMime = inferImageMime(file), mime = actualMime || declaredMime;
  if (mime === "image/heic" || mime === "image/heif") return transcodeToJpeg(file);
  if (supportedMimeTypes.has(mime)) return file.type === mime ? file : new File([file], file.name, { type: mime, lastModified: file.lastModified });
  throw new Error(`Unsupported image format${mime ? ` (${mime})` : ""}. Use JPEG, PNG, or WebP.`);
}

export function uploadPipelineTimeout(input: RequestInfo | URL, init?: RequestInit) {
  const method = String(init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
  const url = String(input instanceof Request ? input.url : input);
  if (method === "PUT" && url.includes("/storage/v1/object/")) return UPLOAD_TIMEOUT_MS;
  if (method === "POST" && (url.includes("/media/complete") || /\/ocr-jobs(?:\?|$)/.test(url))) return API_STAGE_TIMEOUT_MS;
  return 0;
}

function installUploadPipelineWatchdog() {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const timeoutMs = uploadPipelineTimeout(input, init);
    if (!timeoutMs || init?.signal) return nativeFetch(input, init);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await nativeFetch(input, { ...init, signal: controller.signal });
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error("Photo upload timed out before it was fully queued. Please retry.");
      }
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  };
  return () => { window.fetch = nativeFetch; };
}

export default function ImageUploadCompatibility() {
  const [normalizationError, setNormalizationError] = useState("");
  useEffect(() => {
    const restoreFetch = installUploadPipelineWatchdog();
    const bypassOnce = new WeakSet<HTMLInputElement>();
    const handleChange = (event: Event) => {
      const input = event.target; if (!(input instanceof HTMLInputElement) || input.type !== "file") return; if (bypassOnce.delete(input)) return;
      const files = input.files; if (!files || files.length !== 1) return; const file = files[0];
      event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation(); setNormalizationError("");
      void normalizePickedImage(file).then((normalized) => {
        if (normalized === file && normalized.type === file.type) bypassOnce.add(input); else { const transfer = new DataTransfer(); transfer.items.add(normalized); input.files = transfer.files; }
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }).catch((error) => {
        input.value = "";
        const detail = error instanceof Error ? error.message : "Image conversion failed";
        setNormalizationError(`Photo was not uploaded: ${detail}. Please export the photo as JPEG or choose a different photo.`);
      });
    };
    document.addEventListener("change", handleChange, true);
    return () => { document.removeEventListener("change", handleChange, true); restoreFetch(); };
  }, []);
  if (!normalizationError) return null;
  return <div role="alert" style={{position:"fixed",left:16,right:16,bottom:16,zIndex:10000,padding:"12px 16px",border:"1px solid currentColor",borderRadius:8,background:"Canvas",color:"CanvasText",boxShadow:"0 4px 18px rgba(0,0,0,.18)"}}>{normalizationError}</div>;
}
