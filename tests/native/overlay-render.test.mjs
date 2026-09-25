import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
  rmdirSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

for (const state of ["current", "empty", "stale"]) {
  test(
    `native overlay renders ${state} captions without crashing`,
    {
      skip: process.platform !== "win32",
    },
    () => {
      const directory = mkdtempSync(join(tmpdir(), "feelsay-native-render-"));
      const caption = join(directory, "caption.json");
      const bitmap = join(directory, "overlay.bmp");
      try {
        writeFileSync(
          caption,
          JSON.stringify({
            text: state === "empty" ? "" : "Controlled caption fixture",
            committedText:
              state === "empty" ? "" : "Controlled caption fixture",
            provisionalText: "",
            isProvisional: false,
            updatedAtMs: state === "stale" ? 1 : Date.now(),
            maxLines: 2,
          }),
        );
        const env = { ...process.env, FEELSAY_CAPTION_TEXT_FILE: caption };
        delete env.FEELSAY_PARENT_PID;
        delete env.FEELSAY_OVERLAY_CONTROL;
        delete env.FEELSAY_OVERLAY_TOKEN;
        delete env.FEELSAY_OVERLAY_SETTINGS;
        execFileSync(
          resolve(
            process.env.FEELSAY_TEST_EXE ??
              "src-tauri/target/release/feelsay.exe",
          ),
          ["--overlay-render-test", bitmap],
          { env, windowsHide: true, timeout: 15000 },
        );
        const bytes = readFileSync(bitmap);
        assert.equal(bytes.subarray(0, 2).toString(), "BM");
        assert.ok(bytes.readInt32LE(18) >= 280);
        assert.ok(Math.abs(bytes.readInt32LE(22)) >= 110);
      } finally {
        rmSync(caption, { force: true });
        rmSync(bitmap, { force: true });
        rmdirSync(directory);
      }
    },
  );
}
