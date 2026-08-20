// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import {
  extractGpsFromImageBytes,
  gpsExifSegment,
  inferImageMime,
  injectGpsIntoJpeg,
  normalizePickedImage,
  sniffImageMime,
  uploadPipelineTimeout,
} from "./ImageUploadCompatibility";

describe("ImageUploadCompatibility", () => {
  it("infers JPEG for iOS/browser files that omit the MIME type", () => {
    const file = new File(["image-bytes"], "price-board.JPG", { type: "" });
    expect(inferImageMime(file)).toBe("image/jpeg");
  });

  it("recognizes JPEG bytes even when metadata is missing", async () => {
    const file = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xdb])], "photo", { type: "" });
    expect(await sniffImageMime(file)).toBe("image/jpeg");
  });

  it("recognizes HEIC bytes even when iOS declares JPEG", async () => {
    const bytes = new Uint8Array([0,0,0,24,0x66,0x74,0x79,0x70,0x68,0x65,0x69,0x63,0,0,0,0]);
    const file = new File([bytes], "IMG_1234.JPG", { type: "image/jpeg" });
    expect(await sniffImageMime(file)).toBe("image/heic");
  });

  it("restores a supported MIME type from actual bytes", async () => {
    const bytes = new Uint8Array([0xff, 0xd8, 0xff, 0xdb]);
    const file = new File([bytes], "price-board.jpeg", { type: "", lastModified: 123 });
    const normalized = await normalizePickedImage(file);
    expect(normalized.type).toBe("image/jpeg");
    expect(normalized.name).toBe("price-board.jpeg");
    expect(normalized.lastModified).toBe(123);
  });

  it("recognizes HEIC from the filename when the browser omits its MIME type", () => {
    const file = new File(["image-bytes"], "IMG_1234.HEIC", { type: "" });
    expect(inferImageMime(file)).toBe("image/heic");
  });

  it("rejects unknown bytes instead of uploading them under a guessed MIME type", async () => {
    const file = new File(["not-an-image"], "photo.jpg", { type: "image/jpeg" });
    await expect(normalizePickedImage(file)).rejects.toThrow("Unsupported image format");
  });

  it("round-trips southern/eastern GPS through the minimal EXIF segment", () => {
    const segment=gpsExifSegment({latitude:-43.5321,longitude:172.6362});
    const gps=extractGpsFromImageBytes(segment.buffer.slice(segment.byteOffset,segment.byteOffset+segment.byteLength) as ArrayBuffer);
    expect(gps?.latitude).toBeCloseTo(-43.5321,4);
    expect(gps?.longitude).toBeCloseTo(172.6362,4);
  });

  it("injects readable GPS into a newly rendered JPEG", async () => {
    const jpeg=new Blob([new Uint8Array([0xff,0xd8,0xff,0xdb,0,1,2,3,0xff,0xd9])],{type:"image/jpeg"});
    const preserved=await injectGpsIntoJpeg(jpeg,{latitude:-43.5321,longitude:172.6362});
    const gps=extractGpsFromImageBytes(await preserved.arrayBuffer());
    expect(gps?.latitude).toBeCloseTo(-43.5321,4);
    expect(gps?.longitude).toBeCloseTo(172.6362,4);
  });

  it("adds a watchdog only to image-upload pipeline requests", () => {
    expect(uploadPipelineTimeout("https://project.supabase.co/storage/v1/object/upload/sign/private-media/x", {method:"PUT"})).toBe(45_000);
    expect(uploadPipelineTimeout("https://api.example/api/v1/media/complete", {method:"POST"})).toBe(30_000);
    expect(uploadPipelineTimeout("https://api.example/api/v1/ocr-jobs", {method:"POST"})).toBe(30_000);
    expect(uploadPipelineTimeout("https://api.example/api/v1/ocr-jobs?kind=PRICE_BOARD", {method:"GET"})).toBe(0);
    expect(uploadPipelineTimeout("https://api.example/api/v1/admin/stations", {method:"GET"})).toBe(0);
  });
});
