"use client";

import { useEffect } from "react";

const supportedMimeTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const inferredMimeByExtension: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  heic: "image/heic",
  heif: "image/heif",
};

export function inferImageMime(file: File) {
  const declared = file.type.trim().toLowerCase();
  if (declared) return declared;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return inferredMimeByExtension[extension] ?? "";
}

export async function sniffImageMime(file: Blob) {
  const bytes = new Uint8Array(await file.slice(0, 32).arrayBuffer());
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff)
    return "image/jpeg";
  if (
    bytes.length >= 8 &&
    bytes[0] === 0x89 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x4e &&
    bytes[3] === 0x47 &&
    bytes[4] === 0x0d &&
    bytes[5] === 0x0a &&
    bytes[6] === 0x1a &&
    bytes[7] === 0x0a
  )
    return "image/png";
  if (
    bytes.length >= 12 &&
    String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...bytes.slice(8, 12)) === "WEBP"
  )
    return "image/webp";
  if (bytes.length >= 12 && String.fromCharCode(...bytes.slice(4, 8)) === "ftyp") {
    const brand = String.fromCharCode(...bytes.slice(8, 12)).toLowerCase();
    if (["heic", "heix", "hevc", "hevx", "heim", "heis", "mif1", "msf1"].includes(brand))
      return "image/heic";
  }
  return "";
}

function replaceExtension(name: string, extension: string) {
  const dot = name.lastIndexOf(".");
  return `${dot > 0 ? name.slice(0, dot) : name}.${extension}`;
}

async function transcodeToJpeg(file: File) {
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.decoding = "async";
    image.src = objectUrl;
    await image.decode();

    const maximumDimension = 4096;
    const scale = Math.min(
      1,
      maximumDimension / Math.max(image.naturalWidth, image.naturalHeight),
    );
    const width = Math.max(1, Math.round(image.naturalWidth * scale));
    const height = Math.max(1, Math.round(image.naturalHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas is unavailable");
    context.drawImage(image, 0, 0, width, height);
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (result) =>
          result ? resolve(result) : reject(new Error("Image conversion failed")),
        "image/jpeg",
        0.9,
      );
    });
    return new File([blob], replaceExtension(file.name || "photo", "jpg"), {
      type: "image/jpeg",
      lastModified: file.lastModified,
    });
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function normalizePickedImage(file: File) {
  const actualMime = await sniffImageMime(file);
  const declaredMime = inferImageMime(file);
  const mime = actualMime || declaredMime;

  if (mime === "image/heic" || mime === "image/heif") {
    return transcodeToJpeg(file);
  }
  if (supportedMimeTypes.has(mime)) {
    return file.type === mime
      ? file
      : new File([file], file.name, {
          type: mime,
          lastModified: file.lastModified,
        });
  }
  return file;
}

export default function ImageUploadCompatibility() {
  useEffect(() => {
    const bypassOnce = new WeakSet<HTMLInputElement>();

    const handleChange = (event: Event) => {
      const input = event.target;
      if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
      if (bypassOnce.delete(input)) return;
      const files = input.files;
      if (!files || files.length !== 1) return;

      const file = files[0];
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      void normalizePickedImage(file)
        .then((normalized) => {
          if (normalized === file && normalized.type === file.type) {
            bypassOnce.add(input);
          } else {
            const transfer = new DataTransfer();
            transfer.items.add(normalized);
            input.files = transfer.files;
          }
          input.dispatchEvent(new Event("change", { bubbles: true }));
        })
        .catch(() => {
          bypassOnce.add(input);
          input.dispatchEvent(new Event("change", { bubbles: true }));
        });
    };

    document.addEventListener("change", handleChange, true);
    return () => document.removeEventListener("change", handleChange, true);
  }, []);

  return null;
}
