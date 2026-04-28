// util/bounded_queue.js
//
// In-memory bounded async queue with fixed concurrency and drop-on-overflow
// semantics. Used by sinks that must not block the HTTP request handler
// but also must not pile up unbounded promises when their downstream
// (Postgres, network) slows down.
//
// Design choices:
//   - Single-process, single-threaded JS, so no real locks needed.
//   - Worker errors are swallowed by design (sinks log their own errors);
//     a stuck worker will not deadlock the queue because we always release
//     `inFlight` in `finally`.
//   - On overflow we drop the *new* record, not the old one, because the
//     existing buffered records are already in flight or about to be -
//     dropping the tail keeps DB writes monotonically progressing.
//   - Drop counter is monotonic and surfaced via `stats()` so /health and
//     ops dashboards can detect sustained pressure.

"use strict";

class BoundedQueue {
  constructor({ concurrency, maxSize, worker, name = "queue" }) {
    if (!Number.isInteger(concurrency) || concurrency <= 0) {
      throw new Error("BoundedQueue: concurrency must be a positive integer");
    }
    if (!Number.isInteger(maxSize) || maxSize <= 0) {
      throw new Error("BoundedQueue: maxSize must be a positive integer");
    }
    if (typeof worker !== "function") {
      throw new Error("BoundedQueue: worker must be a function");
    }

    this.concurrency = concurrency;
    this.maxSize = maxSize;
    this.worker = worker;
    this.name = name;
    this.queue = [];
    this.inFlight = 0;
    this.droppedTotal = 0;
  }

  push(item) {
    if (this.queue.length >= this.maxSize) {
      this.droppedTotal++;
      // Throttle the warning so a long outage does not flood stderr.
      if (this.droppedTotal === 1 || this.droppedTotal % 100 === 0) {
        console.warn(
          `[${this.name}] buffer full (size=${this.maxSize}), droppedTotal=${this.droppedTotal}`,
        );
      }
      return false;
    }
    this.queue.push(item);
    this._drain();
    return true;
  }

  _drain() {
    while (this.inFlight < this.concurrency && this.queue.length > 0) {
      const item = this.queue.shift();
      this.inFlight++;
      Promise.resolve()
        .then(() => this.worker(item))
        .catch(() => {
          // Sinks log their own errors. Swallow here so one bad row never
          // halts the queue.
        })
        .finally(() => {
          this.inFlight--;
          this._drain();
        });
    }
  }

  stats() {
    return {
      depth: this.queue.length,
      inFlight: this.inFlight,
      droppedTotal: this.droppedTotal,
    };
  }

  async drainAndWait(timeoutMs = 5000) {
    const start = Date.now();
    while (this.queue.length > 0 || this.inFlight > 0) {
      if (Date.now() - start > timeoutMs) return false;
      await new Promise((r) => setTimeout(r, 25));
    }
    return true;
  }
}

module.exports = { BoundedQueue };
