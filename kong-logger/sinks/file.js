// sinks/file.js
//
// Daily-rotated JSONL writer. One file per UTC day at
// ${LOGS_DIR}/access-YYYYMMDD.jsonl. Cheap, self-contained, no external
// dependency.
//
// Reliability notes:
//   - We honour Node stream backpressure: when the underlying write()
//     returns false we wait for "drain" before issuing the next write.
//     This bounds the stream's internal buffer under slow-disk conditions.
//   - The day-rollover path closes the previous stream after swapping the
//     reference. Single-threaded JS means the swap is atomic per tick, so
//     no two writers ever target the same file handle simultaneously.
//   - If the logs directory cannot be created at startup we exit cleanly
//     with code 1 so Docker's restart-on-failure surfaces the error
//     instead of the process silently looping internally.

"use strict";

const fs = require("fs");
const path = require("path");
const { once } = require("events");

class FileSink {
  constructor({ dir }) {
    this.dir = dir;
    this.currentDay = null;
    this.stream = null;
    this._needsDrain = false;

    try {
      fs.mkdirSync(this.dir, { recursive: true });
    } catch (err) {
      console.error(
        `FATAL [file-sink] cannot create logs dir ${this.dir}: ${err.code || err.message}`,
      );
      process.exit(1);
    }
  }

  _dayKey(date) {
    const y = date.getUTCFullYear();
    const m = String(date.getUTCMonth() + 1).padStart(2, "0");
    const d = String(date.getUTCDate()).padStart(2, "0");
    return `${y}${m}${d}`;
  }

  _ensureStream() {
    const day = this._dayKey(new Date());
    if (day === this.currentDay && this.stream) return;

    // Atomic swap (single-threaded JS): assign the new stream first, then
    // ask the old stream to flush + close. Pending writes on the old
    // stream still complete because the stream object holds its own
    // reference until it finishes.
    const oldStream = this.stream;
    const filePath = path.join(this.dir, `access-${day}.jsonl`);
    const next = fs.createWriteStream(filePath, { flags: "a" });
    next.on("error", (err) => {
      console.error("[file-sink] stream error:", err.message);
    });

    this.stream = next;
    this.currentDay = day;
    this._needsDrain = false;

    if (oldStream) {
      oldStream.end();
    }
  }

  async write(record) {
    try {
      this._ensureStream();

      if (this._needsDrain) {
        await once(this.stream, "drain");
        this._needsDrain = false;
      }

      const ok = this.stream.write(JSON.stringify(record) + "\n");
      if (!ok) this._needsDrain = true;
    } catch (err) {
      console.error("[file-sink] failed to write record:", err.message);
    }
  }

  async close() {
    const s = this.stream;
    this.stream = null;
    if (s) {
      await new Promise((resolve) => s.end(resolve));
    }
  }
}

module.exports = { FileSink };
