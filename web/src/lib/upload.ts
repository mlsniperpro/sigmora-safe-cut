/**
 * Client-side checks for `/try` (UI-SPEC §10.2). The server enforces the same
 * limits; these only give fast feedback.
 */

export const MAX_BYTES = 157_286_400; // 150 × 1024 × 1024, the same number WP5 uses
export const MAX_DURATION_S = 60.05; // 60 s plus container rounding
export const CODE_MAX_LENGTH = 64;

const TYPES: Readonly<Record<string, string>> = { ".mp4": "video/mp4", ".mov": "video/quicktime" };

/** Rounds up to one decimal, so a number shown for an over-limit value is never at the limit. */
export function ceilTenth(x: number): string {
  // The 1e-9 slack absorbs floating-point noise (60.1 × 10 = 601.0000000000001), nothing larger.
  return (Math.ceil(x * 10 - 1e-9) / 10).toFixed(1);
}

export function sizeMb(bytes: number): string {
  return ceilTenth(bytes / 1_048_576);
}

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export type FileProblem =
  | { kind: "count"; message: string }
  | { kind: "type"; message: string }
  | { kind: "size"; message: string };

/**
 * Checks file count, type and size. Returns the `content_type` to declare (from
 * the MIME type, or from the extension when the browser gave none).
 */
export function checkFiles(files: ReadonlyArray<Pick<File, "name" | "type" | "size">>): { ok: true; contentType: string } | { ok: false; problem: FileProblem } {
  if (files.length !== 1) return { ok: false, problem: { kind: "count", message: "Drop one clip at a time." } };
  const file = files[0] as Pick<File, "name" | "type" | "size">;
  const fromExtension = TYPES[extensionOf(file.name)];
  const mime = file.type.toLowerCase();
  const mimeOk = mime === "video/mp4" || mime === "video/quicktime";
  // Both checks must pass; an empty MIME string fails only together with the extension.
  const typeOk = fromExtension !== undefined && (mimeOk || mime === "");
  if (!typeOk) return { ok: false, problem: { kind: "type", message: "Safe Cut takes MP4 or MOV video files." } };
  if (file.size > MAX_BYTES) return { ok: false, problem: { kind: "size", message: `This file is ${sizeMb(file.size)} MB. The limit is 150 MB.` } };
  return { ok: true, contentType: mimeOk ? mime : fromExtension };
}

/** The too-long message, from the client's metadata or the server's `failure.duration_s`. */
export function tooLongMessage(durationS: number | null | undefined): string {
  if (durationS === null || durationS === undefined || !Number.isFinite(durationS)) return "This clip is longer than 60 seconds. Trim it and try again.";
  return `This clip is ${ceilTenth(durationS)} seconds long. The limit is 60 seconds. Trim it and try again.`;
}

/** Duration verdict: null means "let `prepare` decide" (metadata missing, NaN or Infinity). */
export function durationProblem(durationS: number | null): string | null {
  if (durationS === null || !Number.isFinite(durationS)) return null;
  return durationS > MAX_DURATION_S ? tooLongMessage(durationS) : null;
}

export function normaliseCode(raw: string): string {
  return raw.trim().slice(0, CODE_MAX_LENGTH);
}
