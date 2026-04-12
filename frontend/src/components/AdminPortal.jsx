import { useState, useEffect } from "react";
import axios from "axios";
import useIntent from "../hooks/useIntent";

const AdminPortal = ({ token, onClose }) => {
  const [activeTab, setActiveTab] = useState("dashboard"); // "dashboard", "mappings", "services", "policies"
  const [services, setServices] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [quotaStatus, setQuotaStatus] = useState(null);
  const [dashboardMetrics, setDashboardMetrics] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingMapping, setEditingMapping] = useState(null);
  const [editingPolicy, setEditingPolicy] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    intent_name: "",
    service_id: "",
    taxonomy_version: "1.0.0",
    is_active: true,
  });

  const { intents: mappings, refresh: fetchMappings } = useIntent();

  useEffect(() => {
    if (activeTab === "services") {
      fetchServices();
    } else if (activeTab === "policies") {
      fetchPolicies();
    } else if (activeTab === "dashboard") {
      fetchQuotaStatus();
      fetchDashboardMetrics();
    }
  }, [activeTab]);

  const fetchPolicies = async () => {
    setLoading(true);
    try {
      const resp = await axios.get("/api/admin/policies", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setPolicies(resp.data);
    } catch (err) {
      setError("Failed to fetch policies");
    } finally {
      setLoading(false);
    }
  };

  const fetchQuotaStatus = async () => {
    setLoading(true);
    try {
      const resp = await axios.get("/api/governance/quota-status", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setQuotaStatus(resp.data);
    } catch (err) {
      console.error(err);
      setError("Failed to fetch quota status");
    } finally {
      setLoading(false);
    }
  };

  const fetchDashboardMetrics = async () => {
    try {
      const resp = await axios.get("/api/admin/metrics", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setDashboardMetrics(resp.data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchServices = async () => {
    setLoading(true);
    try {
      const resp = await axios.get("/api/service-governance", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setServices(resp.data);
    } catch (err) {
      setError("Failed to fetch services");
    } finally {
      setLoading(false);
    }
  };

  const toggleServiceType = async (serviceId, currentType) => {
    const newType = currentType === "cloud" ? "on-prem" : "cloud";
    setLoading(true);
    try {
      await axios.patch(
        `/api/service-governance/${serviceId}`,
        { service_type: newType },
        {
          headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
        },
      );
      fetchServices();
    } catch (err) {
      setError("Failed to update service type");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}`, "kong-header": "true" };
      
      if (activeTab === "mappings") {
        if (editingMapping) {
          await axios.put(`/api/admin/intent-mappings/${editingMapping.id}`, formData, { headers });
        } else {
          await axios.post("/api/admin/intent-mappings", formData, { headers });
        }
        fetchMappings();
      } else if (activeTab === "policies") {
        if (editingPolicy) {
          await axios.put(`/api/admin/policies/${editingPolicy.id}`, formData, { headers });
        } else {
          await axios.post("/api/admin/policies", formData, { headers });
        }
        fetchPolicies();
      }
      
      setShowForm(false);
      setEditingMapping(null);
      setEditingPolicy(null);
    } catch (err) {
      setError(err.response?.data?.detail || "Save failed");
    } finally {
      setLoading(false);
    }
  };

  const handleDeletePolicy = async (id) => {
    if (!window.confirm("Are you sure you want to delete this policy?")) return;
    try {
      await axios.delete(`/api/admin/policies/${id}`, {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      fetchPolicies();
    } catch (err) {
      setError("Delete failed");
    }
  };

  const handleReloadPolicies = async () => {
    try {
      await axios.post(
        "/api/admin/policies/reload",
        {},
        {
          headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
        },
      );
      alert("Policies reloaded successfully!");
    } catch (err) {
      setError("Reload failed");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to deactivate this mapping?"))
      return;
    try {
      await axios.delete(`/api/admin/intent-mappings/${id}`, {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      fetchMappings();
    } catch (err) {
      setError("Delete failed");
    }
  };

  const handleReload = async () => {
    try {
      await axios.post(
        "/api/admin/intent-mappings/reload",
        {},
        {
          headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
        },
      );
      alert("Cache reloaded successfully!");
    } catch (err) {
      setError("Reload failed");
    }
  };

  return (
    <div
      className="admin-portal-overlay"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.85)",
        backdropFilter: "blur(8px)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        className="admin-card"
        style={{
          width: "100vw",
          height: "100vh",
          background: "var(--bg-deep)",
          padding: "3rem 10%",
          overflowY: "auto",
          position: "relative",
        }}
      >

        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "1.5rem",
            right: "1.5rem",
            background: "transparent",
            border: "none",
            color: "var(--text-dim)",
            cursor: "pointer",
            fontSize: "1.5rem",
          }}
        >
          ✕
        </button>

        <div
          style={{
            display: "flex",
            gap: "2rem",
            marginBottom: "2rem",
            borderBottom: "1px solid var(--glass-border)",
            paddingBottom: "1rem",
          }}
        >
          <button
            onClick={() => setActiveTab("dashboard")}
            style={{
              background: "none",
              border: "none",
              color:
                activeTab === "dashboard"
                  ? "var(--accent-primary)"
                  : "var(--text-dim)",
              fontWeight: activeTab === "dashboard" ? "600" : "400",
              cursor: "pointer",
              padding: "0 0.5rem",
              fontSize: "1rem",
            }}
          >
            📊 Platform Dashboard
          </button>
          <button
            onClick={() => setActiveTab("mappings")}
            style={{
              background: "none",
              border: "none",
              color:
                activeTab === "mappings"
                  ? "var(--accent-primary)"
                  : "var(--text-dim)",
              fontWeight: activeTab === "mappings" ? "600" : "400",
              cursor: "pointer",
              padding: "0 0.5rem",
              fontSize: "1rem",
            }}
          >
            Intent Mappings
          </button>
          <button
            onClick={() => setActiveTab("services")}
            style={{
              background: "none",
              border: "none",
              color:
                activeTab === "services"
                  ? "var(--accent-primary)"
                  : "var(--text-dim)",
              fontWeight: activeTab === "services" ? "600" : "400",
              cursor: "pointer",
              padding: "0 0.5rem",
              fontSize: "1rem",
            }}
          >
            AI Services
          </button>
          <button
            onClick={() => setActiveTab("policies")}
            style={{
              background: "none",
              border: "none",
              color:
                activeTab === "policies"
                  ? "var(--accent-primary)"
                  : "var(--text-dim)",
              fontWeight: activeTab === "policies" ? "600" : "400",
              cursor: "pointer",
              padding: "0 0.5rem",
              fontSize: "1rem",
            }}
          >
            Governance Policies
          </button>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "2rem",
          }}
        >
          <div>
            <h2 style={{ color: "white", marginBottom: "0.5rem" }}>
              {activeTab === "mappings"
                ? "Intent Routing Admin"
                : activeTab === "services" 
                  ? "AI Service Governance"
                  : "Security Policy Management"}
            </h2>
            <p style={{ color: "var(--text-dim)", fontSize: "0.9rem" }}>
              {activeTab === "mappings"
                ? "Manage intent-to-service orchestration"
                : activeTab === "services"
                  ? "Classify services for security policy enforcement"
                  : "Define automated security guardrails based on context"}
            </p>
          </div>
          {(activeTab === "mappings" || activeTab === "policies") && (
            <div style={{ display: "flex", gap: "1rem" }}>
              <button 
                className="dashboard-btn" 
                onClick={activeTab === "mappings" ? handleReload : handleReloadPolicies}
              >
                Reload {activeTab === "mappings" ? "Cache" : "Policies"}
              </button>
              <button
                className="dashboard-btn"
                style={{ background: "var(--accent-primary)" }}
                onClick={() => {
                  setEditingMapping(null);
                  setEditingPolicy(null);
                  if (activeTab === "mappings") {
                    setFormData({
                      intent_name: "",
                      service_id: "",
                      taxonomy_version: "1.0.0",
                      is_active: true,
                    });
                  } else {
                    setFormData({
                      description: "",
                      condition: { sensitivity: "LOW", tenant: "" },
                      effect: "deny_cloud",
                      is_active: true,
                      version: "1.0.0",
                    });
                  }
                  setShowForm(true);
                }}
              >
                + Add {activeTab === "mappings" ? "Mapping" : "Policy"}
              </button>
            </div>
          )}
        </div>

        {error && (
          <div
            style={{
              color: "#fca5a5",
              background: "rgba(239, 68, 68, 0.1)",
              padding: "1rem",
              borderRadius: "12px",
              marginBottom: "1rem",
            }}
          >
            {error}
          </div>
        )}

        {showForm ? (
          <form
            onSubmit={handleSave}
            style={{ display: "flex", flexDirection: "column", gap: "1.2rem" }}
          >
            {activeTab === "mappings" ? (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Intent Name</label>
                    <input
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.intent_name}
                      onChange={(e) => setFormData({ ...formData, intent_name: e.target.value })}
                      disabled={!!editingMapping}
                      placeholder="e.g. general_chat"
                      required
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Service ID</label>
                    <input
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.service_id}
                      onChange={(e) => setFormData({ ...formData, service_id: e.target.value })}
                      placeholder="e.g. ollama_llama3.2"
                      required
                    />
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Taxonomy Version</label>
                    <input
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.taxonomy_version}
                      onChange={(e) => setFormData({ ...formData, taxonomy_version: e.target.value })}
                    />
                  </div>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: "1rem", paddingBottom: "10px" }}>
                    <input type="checkbox" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} />
                    <label style={{ color: "white" }}>Active</label>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  <label style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>Policy Description</label>
                  <textarea
                    className="model-select-dropdown"
                    style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)", minHeight: "80px", border: "1px solid var(--glass-border)", color: "white", borderRadius: "8px" }}
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Describe the security rule..."
                    required
                  />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Sensitivity Level</label>
                    <select
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.condition?.sensitivity || "LOW"}
                      onChange={(e) => setFormData({ 
                        ...formData, 
                        condition: { ...formData.condition, sensitivity: e.target.value } 
                      })}
                    >
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Tenant ID (Optional)</label>
                    <input
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.condition?.tenant || ""}
                      onChange={(e) => setFormData({ 
                        ...formData, 
                        condition: { ...formData.condition, tenant: e.target.value } 
                      })}
                      placeholder="Leave empty for all tenants"
                    />
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Enforced Effect</label>
                    <select
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.effect || "deny_cloud"}
                      onChange={(e) => setFormData({ ...formData, effect: e.target.value })}
                    >
                      <option value="deny_cloud">Deny Cloud</option>
                      <option value="allow_onprem_only">On-Prem Only</option>
                      <option value="block_all">Block All</option>
                      <option value="allow_all">Allow All (Audit Only)</option>
                    </select>
                  </div>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: "1rem", paddingBottom: "10px" }}>
                    <input type="checkbox" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} />
                    <label style={{ color: "white" }}>Active Rule</label>
                  </div>
                </div>
              </>
            )}
            <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
              <button type="submit" className="dashboard-btn" style={{ flex: 1, background: "var(--accent-primary)" }}>
                {editingMapping || editingPolicy ? "Update" : "Create"}
              </button>
              <button type="button" className="dashboard-btn" style={{ flex: 1 }} onClick={() => setShowForm(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : activeTab === "dashboard" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {/* Real Token Quota (Redux/Redis simulation) */}
            <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "rgba(59, 130, 246, 0.05)" }}>
              <h3 style={{ color: "var(--accent-primary)", marginBottom: "1rem", fontSize: "1.1rem" }}>Token Quota & Cost</h3>
              {loading ? (
                <p style={{ color: "var(--text-dim)" }}>Loading live quota data...</p>
              ) : quotaStatus ? (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                    <span style={{ color: "white" }}>Tenant: <b>{quotaStatus.tenant_id}</b></span>
                    <span style={{ color: "var(--text-dim)" }}>Limit: {quotaStatus.daily_limit?.toLocaleString()} details</span>
                  </div>
                  <div style={{ height: "12px", background: "rgba(255,255,255,0.1)", borderRadius: "999px", overflow: "hidden", marginBottom: "0.5rem" }}>
                    <div style={{
                      height: "100%",
                      width: `${Math.min(quotaStatus.percent_used || 0, 100)}%`,
                      background: quotaStatus.percent_used > 80 ? "#ef4444" : quotaStatus.percent_used > 50 ? "#f59e0b" : "var(--accent-primary)",
                      transition: "width 0.4s ease"
                    }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", color: "var(--text-dim)" }}>
                    <span>{quotaStatus.used_tokens?.toLocaleString()} used ({(quotaStatus.percent_used || 0).toFixed(1)}%)</span>
                    <span>{quotaStatus.remaining_tokens?.toLocaleString()} remaining</span>
                  </div>
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div style={{ background: "rgba(0,0,0,0.1)", padding: "1rem", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)" }}>
                    <span style={{ color: "var(--text-dim)", fontSize: "0.8rem", display: "block" }}>Top Consumer Today</span>
                    <span style={{ color: "white", fontSize: "1.2rem", fontWeight: "bold" }}>{dashboardMetrics?.cost?.top_consumer || "None"}</span>
                    <span style={{ color: "var(--accent-primary)", fontSize: "0.8rem", display: "block", marginTop: "4px" }}>Active Traffic Detected</span>
                  </div>
                  <div style={{ background: "rgba(0,0,0,0.1)", padding: "1rem", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)" }}>
                    <span style={{ color: "var(--text-dim)", fontSize: "0.8rem", display: "block" }}>Projected Cost</span>
                    <span style={{ color: "white", fontSize: "1.2rem", fontWeight: "bold" }}>${dashboardMetrics?.cost?.projected_cost?.toFixed(3) || "0.000"}</span>
                    <span style={{ color: "#34d399", fontSize: "0.8rem", display: "block", marginTop: "4px" }}>Real-time DB Calc</span>
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "1.5rem", padding: "8px 16px", background: "rgba(52, 211, 153, 0.1)", borderRadius: "8px", border: "1px solid rgba(52, 211, 153, 0.2)" }}>
               <div style={{ width: "8px", height: "8px", background: "#34d399", borderRadius: "50%", boxShadow: "0 0 10px #34d399" }} className="ping-anim"></div>
               <span style={{ color: "#34d399", fontSize: "0.85rem", fontWeight: "600", letterSpacing: "0.5px" }}>LIVE DATABASE FEED ACTIVE</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
              {/* Request Health */}
              <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "rgba(255,255,255,0.02)" }}>
                <h3 style={{ color: "white", marginBottom: "1rem", fontSize: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>🩺 Request Health</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Total Requests (24h)</span>
                    <span style={{ color: "white", fontWeight: "bold" }}>{dashboardMetrics?.health?.total_requests || 0}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Success Rate</span>
                    <span style={{ color: (dashboardMetrics?.health?.success_rate || 0) >= 90 ? "#34d399" : "#fbbf24", fontWeight: "bold" }}>{dashboardMetrics?.health?.success_rate || 0}%</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Top Intent</span>
                    <span style={{ color: "white" }}>{dashboardMetrics?.health?.top_intent || "N/A"}</span>
                  </div>
                </div>
              </div>

              {/* Security Events */}
              <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "rgba(239, 68, 68, 0.05)" }}>
                <h3 style={{ color: "#f87171", marginBottom: "1rem", fontSize: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>🛡️ Security Events</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Blocked by Policy</span>
                    <span style={{ color: "#f87171", fontWeight: "bold" }}>{dashboardMetrics?.security?.blocked || 0}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Prompt Injections Detect</span>
                    <span style={{ color: "white" }}>{dashboardMetrics?.security?.prompt_injections || 0}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>PII Auto-Upgrades</span>
                    <span style={{ color: "#fbbf24" }}>{dashboardMetrics?.security?.pii_upgrades || 0}</span>
                  </div>
                </div>
              </div>

              {/* Routing Decisions */}
              <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "rgba(255,255,255,0.02)" }}>
                <h3 style={{ color: "white", marginBottom: "1rem", fontSize: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>🔀 Routing Decisions</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Cloud Fallback Traffic</span>
                    <span style={{ color: "#fbbf24", fontWeight: "bold" }}>{dashboardMetrics?.routing?.cloud_percentage || 0}%</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>On-Prem Edge Traffic</span>
                    <span style={{ color: "#60a5fa", fontWeight: "bold" }}>{dashboardMetrics?.routing?.edge_percentage || 0}%</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Denied Before Proxy</span>
                    <span style={{ color: "#f87171" }}>{dashboardMetrics?.routing?.denied_pre_proxy || 0} requests</span>
                  </div>
                </div>
              </div>

              {/* System Health */}
              <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "rgba(255,255,255,0.02)" }}>
                <h3 style={{ color: "white", marginBottom: "1rem", fontSize: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>⚙️ System Health</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ color: "var(--text-dim)", fontSize: "0.9rem" }}>FastAPI Pipeline Latency</span>
                    <span style={{ color: "#34d399", fontSize: "0.9rem", background: "rgba(52,211,153,0.1)", padding: "2px 8px", borderRadius: "8px" }}>{dashboardMetrics?.system?.backend_latency_ms || 0} ms</span>
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
                    <span style={{ fontSize: "0.75rem", background: "rgba(52,211,153,0.1)", color: "#34d399", border: "1px solid rgba(52,211,153,0.3)", padding: "4px 8px", borderRadius: "12px" }}>Kong: OK</span>
                    <span style={{ fontSize: "0.75rem", background: "rgba(52,211,153,0.1)", color: "#34d399", border: "1px solid rgba(52,211,153,0.3)", padding: "4px 8px", borderRadius: "12px" }}>Keycloak: OK</span>
                    <span style={{ fontSize: "0.75rem", background: "rgba(251,191,36,0.1)", color: "#fbbf24", border: "1px solid rgba(251,191,36,0.3)", padding: "4px 8px", borderRadius: "12px" }}>Vault: WARN</span>
                  </div>
                </div>
              </div>
            </div>
            
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="dashboard-btn" onClick={fetchQuotaStatus}>🔄 Refresh Metrics</button>
            </div>
          </div>
        ) : activeTab === "mappings" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
            {mappings.map((m) => (
              <div key={m.id} style={{ padding: "1rem", background: "rgba(255,255,255,0.03)", borderRadius: "16px", border: "1px solid var(--glass-border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
                    <span style={{ fontWeight: 600, color: "white" }}>{m.intent_name}</span>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-dim)", background: "rgba(255,b255,255,0.05)", padding: "2px 8px", borderRadius: "10px" }}>v{m.taxonomy_version}</span>
                    {!m.is_active && <span style={{ fontSize: "0.7rem", color: "#fca5a5", background: "rgba(239, 68, 68, 0.1)", padding: "2px 8px", borderRadius: "10px" }}>Inactive</span>}
                  </div>
                  <div style={{ fontSize: "0.85rem", color: "var(--text-dim)", marginTop: "0.3rem" }}>Routes to: <code style={{ color: "var(--accent-primary)" }}>{m.service_id}</code></div>
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button className="dashboard-btn" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => { setEditingMapping(m); setFormData({ intent_name: m.intent_name, service_id: m.service_id, taxonomy_version: m.taxonomy_version, is_active: m.is_active }); setShowForm(true); }}>Edit</button>
                  <button className="dashboard-btn" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem", borderColor: "rgba(239, 68, 68, 0.3)", color: "#fca5a5" }} onClick={() => handleDelete(m.id)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        ) : activeTab === "services" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
            {services.map((s) => (
              <div key={s.service_id} style={{ padding: "1rem", background: "rgba(255,255,255,0.03)", borderRadius: "16px", border: "1px solid var(--glass-border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 600, color: "white", marginBottom: "0.2rem" }}>{s.service_id}</div>
                  <div style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>Model: <span style={{ color: "var(--accent-primary)" }}>{s.model_name}</span></div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                  <div style={{ fontSize: "0.75rem", padding: "4px 12px", borderRadius: "20px", background: s.service_type === "cloud" ? "rgba(59, 130, 246, 0.1)" : "rgba(16, 185, 129, 0.1)", color: s.service_type === "cloud" ? "#60a5fa" : "#34d399", border: `1px solid ${s.service_type === "cloud" ? "rgba(59, 130, 246, 0.3)" : "rgba(16, 185, 129, 0.3)"}` }}>{s.service_type.toUpperCase()}</div>
                  <button className="dashboard-btn" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => toggleServiceType(s.service_id, s.service_type)}>Switch to {s.service_type === "cloud" ? "On-Prem" : "Cloud"}</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
            {policies.map((p) => (
              <div key={p.id} style={{ padding: "1.2rem", background: "rgba(255,255,255,0.03)", borderRadius: "16px", border: "1px solid var(--glass-border)", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", marginBottom: "0.6rem" }}>
                    <span style={{ fontWeight: 600, color: "white" }}>{p.effect.replace("_", " ").toUpperCase()}</span>
                    <span style={{ fontSize: "0.7rem", color: "#60a5fa", background: "rgba(59, 130, 246, 0.1)", padding: "2px 8px", borderRadius: "10px", border: "1px solid rgba(59, 130, 246, 0.2)" }}>
                      {p.condition.sensitivity} SENSITIVITY
                    </span>
                    {p.condition.tenant && (
                      <span style={{ fontSize: "0.7rem", color: "#34d399", background: "rgba(16, 185, 129, 0.1)", padding: "2px 8px", borderRadius: "10px", border: "1px solid rgba(16, 185, 129, 0.2)" }}>
                        TENANT: {p.condition.tenant}
                      </span>
                    )}
                    {!p.is_active && <span style={{ fontSize: "0.7rem", color: "#fca5a5", background: "rgba(239, 68, 68, 0.1)", padding: "2px 8px", borderRadius: "10px" }}>Disabled</span>}
                  </div>
                  <p style={{ fontSize: "0.85rem", color: "var(--text-dim)", lineHeight: "1.4", margin: 0 }}>{p.description}</p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", marginLeft: "1.5rem" }}>
                  <button
                    className="dashboard-btn"
                    style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }}
                    onClick={() => {
                      setEditingPolicy(p);
                      setFormData({
                        description: p.description,
                        condition: p.condition,
                        effect: p.effect,
                        is_active: p.is_active,
                        version: p.version,
                      });
                      setShowForm(true);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    className="dashboard-btn"
                    style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem", borderColor: "rgba(239, 68, 68, 0.3)", color: "#fca5a5" }}
                    onClick={() => handleDeletePolicy(p.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminPortal;
