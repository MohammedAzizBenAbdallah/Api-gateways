// server.js
const express = require("express");
const fs = require("fs");
const app = express();

app.use(express.json());

const logFile = fs.createWriteStream("./kong-logs.json", { flags: "a" });

app.post("/logs", (req, res) => {
  const log = req.body;

  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log(`[${new Date().toISOString()}]`);
  console.log(`${log.request?.method} ${log.request?.uri}`);
  console.log(log.request?.body);
  console.log(`Status  : ${log.response?.status}`);
  console.log(`Latency : ${log.response?.latency}ms`);

  logFile.write(JSON.stringify(log) + "\n");
  res.sendStatus(200);
});

app.listen(9999, "0.0.0.0", () =>
  console.log("✅ Log server on http://localhost:9999"),
);
