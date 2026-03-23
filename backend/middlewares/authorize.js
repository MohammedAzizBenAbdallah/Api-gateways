import pool from "../db.js";

const authorize = async (req, res, next) => {
  console.log(req.user);
  const tenantId = req.user["tenant_id"];
  console.log(tenantId);
  const serviceId = req.params.serviceId || req.headers["x-service-id"];

  if (!tenantId) {
    return res.status(401).json({ message: "Missing X-Tenant-ID header" });
  }

  if (!serviceId) {
    return res.status(400).json({ message: "Missing Service ID" });
  }

  try {
    const result = await pool.query(
      "SELECT allowed FROM tenant_service_permissions WHERE tenant_id = $1 AND service_id = $2",
      [tenantId, serviceId],
    );

    const isAllowed = result.rows.length > 0 && result.rows[0].allowed;

    // Audit Logging
    await pool.query(
      "INSERT INTO permission_audit_logs (tenant_id, service_id, action, performed_by, reason) VALUES ($1, $2, $3, $4, $5)",
      [
        tenantId,
        serviceId,
        isAllowed ? "ALLOW" : "DENY",
        "system",
        isAllowed ? "Policy check passed" : "Policy check failed",
      ],
    );

    if (!isAllowed) {
      return res.status(403).json({
        message: `Forbidden: Tenant '${tenantId}' does not have access to service '${serviceId}'`,
        error_code: "TENANT_RESTRICTED",
      });
    }

    next();
  } catch (err) {
    console.error("Authorization Error:", err.message);
    res
      .status(500)
      .json({ message: "Internal Server Error during authorization" });
  }
};

export default authorize;
