import express from "express";
import fetch from "node-fetch";
import pool from "../db.js";
import authorize from "../middlewares/authorize.js";

const router = express.Router();

router.post("/orchestrate/:serviceId", authorize, async (req, res) => {
  const { serviceId } = req.params;
  const body = req.body;

  try {
    // 1. Fetch provider details including model name
    const serviceResult = await pool.query(
      "SELECT provider_url, provider_type, model_name FROM ai_services WHERE service_id = $1",
      [serviceId],
    );

    if (serviceResult.rows.length === 0) {
      return res
        .status(404)
        .json({ message: `Service '${serviceId}' not found` });
    }

    const { provider_url, provider_type, model_name } = serviceResult.rows[0];

    console.log(
      `Orchestrating → ${serviceId} | model: ${model_name} | url: ${provider_url}`,
    );

    // 2. Build provider-specific payload
    let outboundBody;

    if (provider_type === "ollama") {
      outboundBody = {
        model: model_name, // ← inject model from DB
        messages: body.messages || [
          // ← use messages from request
          { role: "user", content: body.prompt }, // ← or fallback to prompt field
        ],
        stream: false, // ← disable streaming for now
      };
    } else {
      // passthrough for other providers
      outboundBody = body;
    }

    // 3. Forward to Ollama
    const response = await fetch(provider_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(outboundBody),
    });

    const data = await response.json();

    // 4. Return response
    res.status(response.status).json(data);
  } catch (err) {
    console.error("Orchestration Error:", err.message);
    res
      .status(500)
      .json({
        message: "Failed to connect to AI provider",
        error: err.message,
      });
  }
});

export default router;
