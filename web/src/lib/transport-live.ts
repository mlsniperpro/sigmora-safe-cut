/**
 * The live transport: `fetch` for JSON routes and `XMLHttpRequest` for the
 * presigned upload (fetch has no upload progress events).
 */
import { ApiError, type RawResponse, type RequestInit, type Transport } from "./api";

export const UPLOAD_STALL_MS = 30_000;

export function liveTransport(baseUrl: string): Transport {
  return {
    async request({ method, path, body, signal }: RequestInit): Promise<RawResponse> {
      const response = await fetch(`${baseUrl}${path}`, {
        method,
        headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
        ...(body !== undefined && { body: JSON.stringify(body) }),
        ...(signal && { signal }),
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
      });
      const text = await response.text();
      let parsed: unknown = null;
      if (text.length > 0) {
        try {
          parsed = JSON.parse(text);
        } catch {
          parsed = undefined;
        }
      }
      return { status: response.status, headers: response.headers, body: parsed };
    },

    upload(url, file, contentType, onProgress, signal) {
      return new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        let stall: ReturnType<typeof setTimeout> | undefined;
        const fail = (message: string) => {
          clearTimeout(stall);
          reject(new ApiError({ kind: "network", message }));
        };
        const arm = () => {
          clearTimeout(stall);
          stall = setTimeout(() => {
            xhr.abort();
            fail("upload stalled: no progress for 30 s");
          }, UPLOAD_STALL_MS);
        };
        xhr.open("PUT", url);
        // The signature covers Content-Type, so it is always set explicitly (UI-SPEC §10.2).
        xhr.setRequestHeader("Content-Type", contentType);
        xhr.upload.onprogress = (event) => {
          arm();
          if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total);
        };
        xhr.onload = () => {
          clearTimeout(stall);
          if (xhr.status >= 200 && xhr.status < 300) {
            onProgress(1);
            resolve();
          } else {
            fail(`upload failed with HTTP ${xhr.status}`);
          }
        };
        xhr.onerror = () => fail("upload failed: network error");
        signal.addEventListener("abort", () => {
          xhr.abort();
          fail("upload cancelled");
        }, { once: true });
        arm();
        xhr.send(file);
      });
    },
  };
}
