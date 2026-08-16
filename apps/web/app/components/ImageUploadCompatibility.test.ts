// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import {
  inferImageMime,
  normalizePickedImage,
} from "./ImageUploadCompatibility";

describe("ImageUploadCompatibility", () => {
  it("infers JPEG for iOS/browser files that omit the MIME type", () => {
    const file = new File(["image-bytes"], "price-board.JPG", { type: "" });
    expect(inferImageMime(file)).toBe("image/jpeg");
  });

  it("restores a supported MIME type without changing the bytes", async () => {
    const file = new File(["image-bytes"], "price-board.jpeg", {
      type: "",
      lastModified: 123,
    });
    const normalized = await normalizePickedImage(file);

    expect(normalized.type).toBe("image/jpeg");
    expect(normalized.name).toBe("price-board.jpeg");
    expect(normalized.lastModified).toBe(123);
    expect(await normalized.text()).toBe("image-bytes");
  });

  it("recognizes HEIC from the filename when the browser omits its MIME type", () => {
    const file = new File(["image-bytes"], "IMG_1234.HEIC", { type: "" });
    expect(inferImageMime(file)).toBe("image/heic");
  });
});
