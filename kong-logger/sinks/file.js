// sinks/file.js
//
// Daily-rotated JSONL writer. One file per UTC day at
// ${LOGS_DIR}/access-YYYYMMDD.jsonl. Cheap, self-contained, no external
// dependency: works fine for the dev environment and gives an offline
// archive even if the Postgres sink is down.

"use strict";

const fs = require("fs");
const path = require("path");

class FileSink {
  constructor({ dir }) {
    this.dir = dir;
    this.currentDay = null;
    this.stream = null;
    fs.mkdirSync(this.dir, { recursive: true });
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

    if (this.stream) {
      this.stream.end();
      this.stream = null;
    }
    const filePath = path.join(this.dir, `access-${day}.jsonl`);
    this.stream = fs.createWriteStream(filePath, { flags: "a" });
    this.currentDay = day;
  }

  write(record) {
    try {
      this._ensureStream();
      this.stream.write(JSON.stringify(record) + "\n");
    } catch (err) {
      console.error("[file-sink] failed to write record:", err.message);
    }
  }

  async close() {
    if (this.stream) {
      await new Promise((resolve) => this.stream.end(resolve));
      this.stream = null;
    }
  }
}

module.exports = { FileSink };
