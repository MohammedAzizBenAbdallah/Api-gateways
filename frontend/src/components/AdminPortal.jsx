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

  // Security Edge State
  const [securityPatterns, setSecurityPatterns] = useState([]);
  const [editingPattern, setEditingPattern] = useState(null);
  const [kongRoutes, setKongRoutes] = useState([]);
  const [kongPlugins, setKongPlugins] = useState([]);
  const [pluginCatalog, setPluginCatalog] = useState([]);
  const [showPluginModal, setShowPluginModal] = useState(false);
  const [selectedPlugin, setSelectedPlugin] = useState(null);
  const [pluginFormData, setPluginFormData] = useState({});
  const [pluginScope, setPluginScope] = useState("global");
  const [pluginRouteId, setPluginRouteId] = useState("");
  const [securitySubTab, setSecuritySubTab] = useState("routes"); // routes, marketplace, active, patterns, feed, quotas
  const [securityScore, setSecurityScore] = useState(null);
  const [securityEvents, setSecurityEvents] = useState([]);
  const [quotasList, setQuotasList] = useState([]);
  const [observabilitySubTab, setObservabilitySubTab] = useState("kong"); // kong, fastapi
  const [activeCategory, setActiveCategory] = useState("all"); // plugin marketplace category filter

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
    } else if (activeTab === "security") {
      fetchSecurityPatterns();
      fetchKongRoutes();
      fetchKongPlugins();
      fetchPluginCatalog();
      fetchSecurityScore();
      fetchSecurityEvents();
      fetchQuotasList();
    }
  }, [activeTab]);

  // ── SOC Live Polling ──────────────────────────────────────────────────────
  useEffect(() => {
    let interval;
    if (activeTab === "security") {
        // Initial fetch is already handled by the effect above
        interval = setInterval(() => {
            fetchSecurityScore();
            fetchSecurityEvents();
        }, 10000); // Poll every 10s for a "Live" feel
    }
    return () => {
        if (interval) clearInterval(interval);
    };
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

  const fetchSecurityPatterns = async () => {
    setLoading(true);
    try {
        const resp = await axios.get("/api/admin/security-patterns", {
            headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
        });
        setSecurityPatterns(resp.data);
    } catch (err) {
        setError("Failed to fetch security patterns");
    } finally {
        setLoading(false);
    }
  };

  const fetchKongRoutes = async () => {
    try {
      const resp = await axios.get("/api/admin/gateway/routes", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setKongRoutes(resp.data);
    } catch (err) {
      console.error("Failed to fetch Kong routes", err);
    }
  };

  const fetchKongPlugins = async () => {
    try {
      const resp = await axios.get("/api/admin/gateway/plugins", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setKongPlugins(resp.data);
    } catch (err) {
      console.error("Failed to fetch Kong plugins", err);
    }
  };

  const fetchPluginCatalog = async () => {
    try {
      const resp = await axios.get("/api/admin/gateway/plugin-catalog", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setPluginCatalog(resp.data);
    } catch (err) {
      console.error("Failed to fetch plugin catalog", err);
    }
  };

  const fetchSecurityScore = async () => {
    try {
      const resp = await axios.get("/api/admin/security/score", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setSecurityScore(resp.data);
    } catch (err) {
      console.error("Failed to fetch security score", err);
    }
  };

  const fetchSecurityEvents = async () => {
    try {
      const resp = await axios.get("/api/admin/security/events", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setSecurityEvents(resp.data);
    } catch (err) {
      console.error("Failed to fetch security events", err);
    }
  };

  const fetchQuotasList = async () => {
    try {
      const resp = await axios.get("/api/admin/quotas", {
        headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
      });
      setQuotasList(resp.data.tenants || []);
    } catch (err) {
      console.error("Failed to fetch quotas", err);
    }
  };

  const handleApplyPlugin = async () => {
    if (!selectedPlugin) return;
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}`, "kong-header": "true" };
      // Build config from form data, converting comma-separated strings to arrays
      const config = {};
      for (const field of selectedPlugin.fields) {
        let val = pluginFormData[field.key];
        if (val === undefined || val === "") {
          if (field.required) {
            val = field.default;
          } else {
            continue;
          }
        }
        // Determine if this field is a comma-separated list that Kong expects as an array
        const isArrayField = field.type === "array" || (
          field.type === "text" && typeof val === "string" &&
          ["allow", "deny", "origins", "methods", "headers",
           "uri_param_names", "cookie_names", "claims_to_verify",
           "key_names", "scopes", "response_code", "request_method", "content_type"
          ].includes(field.key)
        );
        if (isArrayField && typeof val === "string") {
          config[field.key] = val.split(",").map(s => s.trim()).filter(Boolean);
        } else if (field.type === "number") {
          config[field.key] = Number(val);
        } else if (field.type === "boolean") {
          config[field.key] = val === true || val === "true";
        } else {
          config[field.key] = val;
        }
      }
      const payload = {
        name: selectedPlugin.name,
        config,
        route_id: pluginScope === "route" ? pluginRouteId : null,
        enabled: true,
      };
      await axios.post("/api/admin/gateway/plugins", payload, { headers });
      setShowPluginModal(false);
      setSelectedPlugin(null);
      setPluginFormData({});
      fetchKongPlugins();
      fetchKongRoutes();
    } catch (err) {
      console.error("Plugin apply error:", err.response?.status, err.response?.data);
      const detail = err.response?.data?.detail || err.response?.data?.message || JSON.stringify(err.response?.data) || err.message || "Failed to apply plugin";
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleTogglePlugin = async (pluginId, currentEnabled) => {
    try {
      const headers = { Authorization: `Bearer ${token}`, "kong-header": "true" };
      await axios.patch(`/api/admin/gateway/plugins/${pluginId}`, { enabled: !currentEnabled }, { headers });
      fetchKongPlugins();
      fetchKongRoutes();
    } catch (err) {
      setError("Failed to toggle plugin");
    }
  };

  const handleDeleteKongPlugin = async (pluginId) => {
    if (!window.confirm("Remove this plugin from Kong Gateway?")) return;
    try {
      const headers = { Authorization: `Bearer ${token}`, "kong-header": "true" };
      await axios.delete(`/api/admin/gateway/plugins/${pluginId}`, { headers });
      fetchKongPlugins();
      fetchKongRoutes();
    } catch (err) {
      setError("Failed to delete plugin");
    }
  };

  const handleUpdateQuota = async (tenantId, maxTokens, resetPeriod, isActive) => {
    try {
      const headers = { Authorization: `Bearer ${token}`, "kong-header": "true" };
      await axios.put(`/api/admin/quotas/${tenantId}`, {
        max_tokens: Number(maxTokens),
        reset_period: resetPeriod,
        is_active: isActive
      }, { headers });
      fetchQuotasList();
    } catch (err) {
      setError("Failed to update quota");
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
      } else if (activeTab === "security") {
        await axios.post("/api/admin/security-patterns", formData, { headers });
        await axios.post("/api/admin/security-patterns/reload", {}, { headers });
        fetchSecurityPatterns();
      }
      
      setShowForm(false);
      setEditingMapping(null);
      setEditingPolicy(null);
      setEditingPattern(null);
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

  const handleDeletePattern = async (id) => {
    if (!window.confirm("Are you sure you want to delete this injection pattern rule?")) return;
    try {
        const headers = { Authorization: `Bearer ${token}`, "kong-header": "true" };
        await axios.delete(`/api/admin/security-patterns/${id}`, { headers });
        await axios.post("/api/admin/security-patterns/reload", {}, { headers });
        fetchSecurityPatterns();
    } catch (err) {
        setError("Delete failed");
    }
  };

  // (Rate limit handlers replaced by generic plugin system above)

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
        background: "var(--overlay-bg)",
        backdropFilter: "blur(12px)",
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
          <button
            onClick={() => setActiveTab("security")}
            style={{
              background: "none",
              border: "none",
              color:
                activeTab === "security"
                  ? "#ef4444"
                  : "var(--text-dim)",
              fontWeight: activeTab === "security" ? "600" : "400",
              cursor: "pointer",
              padding: "0 0.5rem",
              fontSize: "1rem",
            }}
          >
            🛡️ Edge & App Security
          </button>
          <button
            onClick={() => setActiveTab("observability")}
            style={{
              background: "none",
              border: "none",
              color:
                activeTab === "observability"
                  ? "#3b82f6"
                  : "var(--text-dim)",
              fontWeight: activeTab === "observability" ? "600" : "400",
              cursor: "pointer",
              padding: "0 0.5rem",
              fontSize: "1rem",
            }}
          >
            📈 Observability
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
            <h2 style={{ color: "var(--text-header)", marginBottom: "0.5rem" }}>
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
            ) : activeTab === "policies" ? (
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
            ) : activeTab === "security" ? (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Pattern Name (e.g. bypass_rule)</label>
                    <input
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.name || ""}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Score Weight (1.0 = automatic block)</label>
                    <input
                      type="number"
                      step="0.1"
                      className="model-select-dropdown"
                      style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                      value={formData.weight || 1.0}
                      onChange={(e) => setFormData({ ...formData, weight: parseFloat(e.target.value) })}
                      required
                    />
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  <label style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>Regular Expression</label>
                  <input
                    className="model-select-dropdown"
                    style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)", fontFamily: "monospace", color: "#fca5a5" }}
                    value={formData.pattern || ""}
                    onChange={(e) => setFormData({ ...formData, pattern: e.target.value })}
                    placeholder="e.g. \b(DAN|Do Anything Now)\b"
                    required
                  />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  <label style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>Description</label>
                  <input
                    className="model-select-dropdown"
                    style={{ width: "100%", padding: "12px", background: "rgba(0,0,0,0.2)" }}
                    value={formData.description || ""}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Describe what this pattern blocks..."
                  />
                </div>
              </>
            ) : null}
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
                <h3 style={{ color: "var(--text-header)", marginBottom: "1rem", fontSize: "1.1rem" }}>Token Quota & Cost</h3>
              {loading ? (
                <p style={{ color: "var(--text-dim)" }}>Loading live quota data...</p>
              ) : quotaStatus ? (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                    <span style={{ color: "var(--text-header)" }}>Tenant: <b>{quotaStatus.tenant_id}</b></span>
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
                  <div style={{ background: "var(--bg-card)", padding: "1rem", borderRadius: "12px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)" }}>
                    <span style={{ color: "var(--text-dim)", fontSize: "0.8rem", display: "block" }}>Top Consumer Today</span>
                    <span style={{ color: "var(--text-header)", fontSize: "1.2rem", fontWeight: "bold" }}>{dashboardMetrics?.cost?.top_consumer || "None"}</span>
                    <span style={{ color: "var(--accent-primary)", fontSize: "0.8rem", display: "block", marginTop: "4px" }}>Active Traffic Detected</span>
                  </div>
                  <div style={{ background: "var(--bg-card)", padding: "1rem", borderRadius: "12px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)" }}>
                    <span style={{ color: "var(--text-dim)", fontSize: "0.8rem", display: "block" }}>Projected Cost</span>
                    <span style={{ color: "var(--text-header)", fontSize: "1.2rem", fontWeight: "bold" }}>${dashboardMetrics?.cost?.projected_cost?.toFixed(3) || "0.000"}</span>
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
              <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "var(--bg-card)", boxShadow: "var(--shadow-premium)" }}>
                <h3 style={{ color: "var(--text-header)", marginBottom: "1rem", fontSize: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>🩺 Request Health</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Total Requests (24h)</span>
                    <span style={{ color: "var(--text-header)", fontWeight: "bold" }}>{dashboardMetrics?.health?.total_requests || 0}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Success Rate</span>
                    <span style={{ color: (dashboardMetrics?.health?.success_rate || 0) >= 90 ? "#34d399" : "#fbbf24", fontWeight: "bold" }}>{dashboardMetrics?.health?.success_rate || 0}%</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>Top Intent</span>
                    <span style={{ color: "var(--text-header)" }}>{dashboardMetrics?.health?.top_intent || "N/A"}</span>
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
                    <span style={{ color: "var(--text-header)" }}>{dashboardMetrics?.security?.prompt_injections || 0}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-dim)" }}>PII Auto-Upgrades</span>
                    <span style={{ color: "#fbbf24" }}>{dashboardMetrics?.security?.pii_upgrades || 0}</span>
                  </div>
                </div>
              </div>

              {/* Routing Decisions */}
              <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "var(--bg-card)", boxShadow: "var(--shadow-premium)" }}>
                <h3 style={{ color: "var(--text-header)", marginBottom: "1rem", fontSize: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>🔀 Routing Decisions</h3>
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
              <div style={{ border: "1px solid var(--glass-border)", borderRadius: "16px", padding: "1.5rem", background: "var(--bg-card)", boxShadow: "var(--shadow-premium)" }}>
                <h3 style={{ color: "var(--text-header)", marginBottom: "1rem", fontSize: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>⚙️ System Health</h3>
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
              <div key={m.id} style={{ padding: "1rem", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-header)" }}>{m.intent_name}</span>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-dim)", background: "var(--bg-deep)", padding: "2px 8px", borderRadius: "10px" }}>v{m.taxonomy_version}</span>
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
              <div key={s.service_id} style={{ padding: "1rem", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 600, color: "var(--text-header)", marginBottom: "0.2rem" }}>{s.service_id}</div>
                  <div style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>Model: <span style={{ color: "var(--accent-primary)" }}>{s.model_name}</span></div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                  <div style={{ fontSize: "0.75rem", padding: "4px 12px", borderRadius: "20px", background: s.service_type === "cloud" ? "rgba(59, 130, 246, 0.1)" : "rgba(16, 185, 129, 0.1)", color: s.service_type === "cloud" ? "#60a5fa" : "#34d399", border: `1px solid ${s.service_type === "cloud" ? "rgba(59, 130, 246, 0.3)" : "rgba(16, 185, 129, 0.3)"}` }}>{s.service_type.toUpperCase()}</div>
                  <button className="dashboard-btn" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => toggleServiceType(s.service_id, s.service_type)}>Switch to {s.service_type === "cloud" ? "On-Prem" : "Cloud"}</button>
                </div>
              </div>
            ))}
          </div>
        ) : activeTab === "policies" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
            {policies.map((p) => (
              <div key={p.id} style={{ padding: "1.2rem", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", marginBottom: "0.6rem" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-header)" }}>{p.effect.replace("_", " ").toUpperCase()}</span>
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
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            
            {/* ── SECURITY SCORE GAUGE ── */}
            {securityScore && (
              <div style={{ padding: "1.5rem", borderRadius: "16px", background: "var(--bg-card)", border: `1px solid ${securityScore.score >= 80 ? 'rgba(52,211,153,0.3)' : securityScore.score >= 50 ? 'rgba(251,191,36,0.3)' : 'rgba(239,68,68,0.3)'}`, boxShadow: "var(--shadow-premium)", display: "flex", alignItems: "center", gap: "2rem" }}>
                <div style={{ width: "100px", height: "100px", borderRadius: "50%", background: "var(--bg-deep)", display: "flex", alignItems: "center", justifyContent: "center", border: `4px solid ${securityScore.score >= 80 ? '#34d399' : securityScore.score >= 50 ? '#fbbf24' : '#ef4444'}`, boxShadow: `0 0 20px ${securityScore.score >= 80 ? 'rgba(52,211,153,0.2)' : securityScore.score >= 50 ? 'rgba(251,191,36,0.2)' : 'rgba(239,68,68,0.2)'}` }}>
                  <span style={{ fontSize: "2rem", fontWeight: 800, color: securityScore.score >= 80 ? '#34d399' : securityScore.score >= 50 ? '#fbbf24' : '#ef4444' }}>{securityScore.score}</span>
                </div>
                <div style={{ flex: 1 }}>
                  <h2 style={{ margin: "0 0 0.5rem 0", color: "var(--text-header)", fontSize: "1.2rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    Platform Security Health
                    <span style={{ fontSize: "0.75rem", padding: "3px 10px", borderRadius: "12px", background: securityScore.score >= 80 ? 'rgba(52,211,153,0.1)' : securityScore.score >= 50 ? 'rgba(251,191,36,0.1)' : 'rgba(239,68,68,0.1)', color: securityScore.score >= 80 ? '#34d399' : securityScore.score >= 50 ? '#fbbf24' : '#ef4444' }}>{securityScore.grade}</span>
                  </h2>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
                      <span style={{ color: "var(--text-dim)" }}>Edge Plugins</span>
                      <span style={{ color: "var(--text-header)" }}>{securityScore.breakdown.kong_edge.points}/{securityScore.breakdown.kong_edge.max}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
                      <span style={{ color: "var(--text-dim)" }}>AI Patterns</span>
                      <span style={{ color: "var(--text-header)" }}>{securityScore.breakdown.ai_patterns.points}/{securityScore.breakdown.ai_patterns.max}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
                      <span style={{ color: "var(--text-dim)" }}>Recent Threats</span>
                      <span style={{ color: "var(--text-header)" }}>{securityScore.breakdown.threat_defense.points}/{securityScore.breakdown.threat_defense.max}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
                      <span style={{ color: "var(--text-dim)" }}>PII Engine</span>
                      <span style={{ color: "var(--text-header)" }}>{securityScore.breakdown.pii_redaction.points}/{securityScore.breakdown.pii_redaction.max}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Security Sub-Navigation */}
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {[{key:"routes",label:"🌐 Routes & Services"},{key:"marketplace",label:"🛒 Plugin Marketplace"},{key:"active",label:"⚡ Active Plugins"},{key:"patterns",label:"🛡️ AI Threat Patterns"},{key:"feed",label:"📡 Live Threat Feed"},{key:"quotas",label:"💰 Quotas"}].map(t => (
                <button key={t.key} onClick={() => setSecuritySubTab(t.key)} style={{
                  padding: "8px 16px", borderRadius: "10px", border: securitySubTab === t.key ? "1px solid var(--accent-primary)" : "1px solid var(--glass-border)",
                  background: securitySubTab === t.key ? "rgba(99, 102, 241, 0.15)" : "var(--bg-card)",
                  color: securitySubTab === t.key ? "var(--accent-primary)" : "var(--text-dim)",
                  cursor: "pointer", fontSize: "0.85rem", fontWeight: securitySubTab === t.key ? "600" : "400",
                  transition: "all 0.2s ease"
                }}>{t.label}</button>
              ))}
            </div>

            {/* ── SUB-TAB: Routes Overview ── */}
            {securitySubTab === "routes" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h3 style={{ color: "var(--text-header)", margin: 0 }}>Kong Gateway Routes</h3>
                    <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: "0.3rem 0 0 0" }}>All routes registered in your Kong API Gateway with their active security plugins.</p>
                  </div>
                  <button className="dashboard-btn" onClick={() => { fetchKongRoutes(); fetchKongPlugins(); }} style={{ fontSize: "0.85rem" }}>🔄 Refresh</button>
                </div>
                {kongRoutes.length === 0 ? (
                  <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-dim)", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)" }}>
                    {loading ? "Loading routes from Kong..." : "No routes found. Is Kong Gateway running?"}
                  </div>
                ) : kongRoutes.map(route => (
                  <div key={route.id} style={{ padding: "1.2rem", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
                        <span style={{ fontWeight: 700, color: "var(--text-header)", fontSize: "1.05rem" }}>{route.name}</span>
                        <code style={{ fontSize: "0.8rem", background: "rgba(99, 102, 241, 0.1)", color: "var(--accent-primary)", padding: "3px 10px", borderRadius: "8px" }}>{(route.paths || []).join(", ")}</code>
                      </div>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-dim)", background: "var(--bg-deep)", padding: "3px 10px", borderRadius: "8px" }}>→ {route.service_name}</span>
                    </div>
                    <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                      {route.plugins.length === 0 ? (
                        <span style={{ fontSize: "0.75rem", color: "var(--text-dim)", fontStyle: "italic" }}>No plugins applied</span>
                      ) : route.plugins.map(p => (
                        <span key={p.id} style={{
                          fontSize: "0.7rem", padding: "3px 10px", borderRadius: "20px",
                          background: p.enabled ? "rgba(52, 211, 153, 0.1)" : "rgba(239, 68, 68, 0.1)",
                          color: p.enabled ? "#34d399" : "#f87171",
                          border: `1px solid ${p.enabled ? "rgba(52, 211, 153, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
                        }}>{p.enabled ? "✓" : "✗"} {p.name}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ── SUB-TAB: Plugin Marketplace ── */}
            {securitySubTab === "marketplace" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h3 style={{ color: "var(--text-header)", margin: 0 }}>Plugin Marketplace</h3>
                    <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: "0.3rem 0 0 0" }}>
                      {pluginCatalog.length} plugins available — click any card to configure and apply it to your gateway.
                    </p>
                  </div>
                </div>
                {/* Category filter pills */}
                {(() => {
                  const categories = ["all", ...new Set(pluginCatalog.map(p => p.category))];
                  const categoryColors = { traffic: "#f59e0b", security: "#ef4444", auth: "#8b5cf6", ai: "#06b6d4", logging: "#10b981", transformation: "#6366f1" };
                  const filtered = activeCategory === "all" ? pluginCatalog : pluginCatalog.filter(p => p.category === activeCategory);
                  return (
                    <>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {categories.map(cat => (
                          <button key={cat} onClick={() => setActiveCategory(cat)} style={{
                            padding: "5px 14px", borderRadius: "20px", fontSize: "0.78rem", fontWeight: 600, cursor: "pointer",
                            textTransform: "capitalize", border: "1px solid",
                            borderColor: activeCategory === cat ? (categoryColors[cat] || "var(--accent-primary)") : "var(--glass-border)",
                            background: activeCategory === cat ? `${(categoryColors[cat] || "#6366f1")}20` : "transparent",
                            color: activeCategory === cat ? (categoryColors[cat] || "var(--accent-primary)") : "var(--text-dim)",
                          }}>{cat === "all" ? `🔌 All (${pluginCatalog.length})` : `${cat}`}</button>
                        ))}
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
                        {filtered.map(plugin => {
                          const catColor = categoryColors[plugin.category] || "#60a5fa";
                          return (
                            <div key={plugin.name} onClick={() => {
                              setSelectedPlugin(plugin);
                              const defaults = {};
                              plugin.fields.forEach(f => { defaults[f.key] = f.default; });
                              setPluginFormData(defaults);
                              setPluginScope("global");
                              setPluginRouteId("");
                              setError(null);
                              setShowPluginModal(true);
                            }} style={{
                              padding: "1.2rem", background: "var(--bg-card)", borderRadius: "16px",
                              border: "1px solid var(--glass-border)", cursor: "pointer",
                              transition: "all 0.2s ease", boxShadow: "var(--shadow-premium)",
                            }}
                            onMouseEnter={e => { e.currentTarget.style.borderColor = catColor; e.currentTarget.style.transform = "translateY(-2px)"; }}
                            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--glass-border)"; e.currentTarget.style.transform = "translateY(0)"; }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
                                <span style={{ fontWeight: 700, color: "var(--text-header)", fontSize: "1rem" }}>{plugin.label}</span>
                                <span style={{ fontSize: "0.65rem", padding: "2px 8px", borderRadius: "10px", background: `${catColor}20`, color: catColor, border: `1px solid ${catColor}40`, textTransform: "uppercase", fontWeight: 600 }}>{plugin.category}</span>
                              </div>
                              <p style={{ fontSize: "0.82rem", color: "var(--text-dim)", lineHeight: 1.5, margin: 0 }}>{plugin.description}</p>
                              <div style={{ marginTop: "0.8rem", display: "flex", justifyContent: "flex-end" }}>
                                <span style={{ fontSize: "0.75rem", color: "var(--accent-primary)", fontWeight: 600 }}>Click to apply →</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  );
                })()}
              </div>
            )}

            {/* ── SUB-TAB: Active Plugins ── */}
            {securitySubTab === "active" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h3 style={{ color: "var(--text-header)", margin: 0 }}>Active Plugins</h3>
                    <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: "0.3rem 0 0 0" }}>All plugins currently running on your Kong Gateway. Toggle or remove them with one click.</p>
                  </div>
                  <button className="dashboard-btn" onClick={fetchKongPlugins} style={{ fontSize: "0.85rem" }}>🔄 Refresh</button>
                </div>
                {kongPlugins.length === 0 ? (
                  <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-dim)", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)" }}>
                    No active plugins. Go to the Marketplace to apply one.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
                    {kongPlugins.map(p => (
                      <div key={p.id} style={{ padding: "1rem", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", marginBottom: "0.3rem" }}>
                            <span style={{ fontWeight: 700, color: "var(--text-header)" }}>{p.name}</span>
                            <span style={{
                              fontSize: "0.65rem", padding: "2px 8px", borderRadius: "10px",
                              background: p.scope === "global" ? "rgba(99, 102, 241, 0.1)" : "rgba(251, 191, 36, 0.1)",
                              color: p.scope === "global" ? "#818cf8" : "#fbbf24",
                              border: `1px solid ${p.scope === "global" ? "rgba(99, 102, 241, 0.3)" : "rgba(251, 191, 36, 0.3)"}`,
                              textTransform: "uppercase", fontWeight: 600
                            }}>{p.scope}{p.scope_target ? ` (${p.scope_target.substring(0,8)}...)` : ""}</span>
                            <span style={{
                              fontSize: "0.65rem", padding: "2px 8px", borderRadius: "10px",
                              background: p.enabled ? "rgba(52, 211, 153, 0.1)" : "rgba(239, 68, 68, 0.1)",
                              color: p.enabled ? "#34d399" : "#f87171",
                            }}>{p.enabled ? "● ACTIVE" : "○ DISABLED"}</span>
                          </div>
                          <code style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>{JSON.stringify(p.config || {}).substring(0, 120)}{JSON.stringify(p.config || {}).length > 120 ? "..." : ""}</code>
                        </div>
                        <div style={{ display: "flex", gap: "0.5rem", marginLeft: "1rem" }}>
                          <button className="dashboard-btn" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem", background: p.enabled ? "rgba(239, 68, 68, 0.1)" : "rgba(52, 211, 153, 0.1)", color: p.enabled ? "#f87171" : "#34d399", border: `1px solid ${p.enabled ? "rgba(239, 68, 68, 0.3)" : "rgba(52, 211, 153, 0.3)"}` }}
                            onClick={() => handleTogglePlugin(p.id, p.enabled)}>{p.enabled ? "Disable" : "Enable"}</button>
                          <button className="dashboard-btn" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem", borderColor: "rgba(239, 68, 68, 0.3)", color: "#fca5a5" }}
                            onClick={() => handleDeleteKongPlugin(p.id)}>Remove</button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── SUB-TAB: AI Threat Patterns ── */}
            {securitySubTab === "patterns" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h3 style={{ color: "#f87171", margin: 0 }}>🛡️ Prompt Injection Patterns</h3>
                    <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: "0.3rem 0 0 0" }}>Regex rules that block malicious AI prompts before they reach the model.</p>
                  </div>
                  <button className="dashboard-btn" style={{ background: "#ef4444", fontSize: "0.85rem" }} onClick={() => { setFormData({name: "", pattern: "", weight: 1.0, description: "", is_active: true}); setShowForm(true); }}>+ Add Pattern</button>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
                  {securityPatterns.map((pat) => (
                    <div key={pat.id} style={{ padding: "1rem", background: "var(--bg-card)", borderRadius: "12px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)", display: "flex", justifyContent: "space-between" }}>
                      <div>
                        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.3rem" }}>
                          <span style={{ fontWeight: "bold", color: "var(--text-header)" }}>{pat.name}</span>
                          <span style={{ fontSize: "0.7rem", color: "#fbbf24", background: "rgba(251, 191, 36, 0.1)", padding: "2px 8px", borderRadius: "10px" }}>Weight: {pat.weight}</span>
                        </div>
                        <code style={{ fontSize: "0.8rem", color: "#fca5a5", background: "rgba(0,0,0,0.4)", padding: "3px 8px", borderRadius: "6px" }}>{pat.pattern}</code>
                        <p style={{ fontSize: "0.8rem", color: "var(--text-dim)", margin: "0.3rem 0 0 0" }}>{pat.description}</p>
                      </div>
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <button className="dashboard-btn" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem", background: "transparent", borderColor: "rgba(239, 68, 68, 0.3)", color: "#fca5a5" }} onClick={() => handleDeletePattern(pat.id)}>Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── SUB-TAB: Live Threat Feed ── */}
            {securitySubTab === "feed" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h3 style={{ color: "#f87171", margin: 0 }}>📡 Live Threat Feed</h3>
                    <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: "0.3rem 0 0 0" }}>Real-time stream of blocked attacks and security events across all tenants.</p>
                  </div>
                  <button className="dashboard-btn" style={{ fontSize: "0.85rem" }} onClick={fetchSecurityEvents}>🔄 Refresh</button>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
                  {securityEvents.length === 0 ? (
                    <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-dim)", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)" }}>
                      No threats detected recently. Your system is safe.
                    </div>
                  ) : securityEvents.map(event => (
                    <div key={event.id} style={{
                      padding: "1rem", background: "var(--bg-card)", borderRadius: "12px",
                      border: `1px solid ${event.decision === 'blocked' ? 'rgba(239, 68, 68, 0.3)' : event.decision === 'redacted' ? 'rgba(251, 191, 36, 0.3)' : 'rgba(52, 211, 153, 0.3)'}`,
                      borderLeft: `4px solid ${event.decision === 'blocked' ? '#ef4444' : event.decision === 'redacted' ? '#fbbf24' : '#34d399'}`,
                      boxShadow: "var(--shadow-premium)",
                      animation: (new Date() - new Date(event.created_at)) < 60000 && event.decision === 'blocked' ? "pulseRed 2s infinite" : "none"
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                          <span style={{ fontWeight: "bold", color: "var(--text-header)" }}>{event.event_type === "prompt_injection" ? "🛡️ Injection" : "🕵️ PII Redaction"}</span>
                          <span style={{ fontSize: "0.8rem", color: "var(--text-dim)" }}>Tenant: <code style={{color: "var(--accent-primary)"}}>{event.tenant_id}</code></span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
                          <span style={{ fontSize: "0.75rem", padding: "2px 8px", borderRadius: "10px", background: "var(--bg-deep)", color: "var(--text-dim)" }}>
                            Score: {event.score || 0}
                          </span>
                          <span style={{ fontSize: "0.75rem", padding: "2px 8px", borderRadius: "10px", fontWeight: "bold",
                            background: event.decision === 'blocked' ? 'rgba(239, 68, 68, 0.1)' : event.decision === 'redacted' ? 'rgba(251, 191, 36, 0.1)' : 'rgba(52, 211, 153, 0.1)',
                            color: event.decision === 'blocked' ? '#ef4444' : event.decision === 'redacted' ? '#fbbf24' : '#34d399' }}>
                            {event.decision.toUpperCase()}
                          </span>
                        </div>
                      </div>
                      <div style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>
                        Patterns matched: <span style={{ color: "var(--text-header)" }}>{(event.matched_patterns || "None").replace(/[\[\]"]/g, "")}</span>
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-dim)", marginTop: "0.5rem" }}>
                        {new Date(event.created_at).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── SUB-TAB: Quotas ── */}
            {securitySubTab === "quotas" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h3 style={{ color: "var(--text-header)", margin: 0 }}>💰 Quota Manager</h3>
                    <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: "0.3rem 0 0 0" }}>Visually manage AI token budgets per tenant to prevent cost overruns.</p>
                  </div>
                  <button className="dashboard-btn" style={{ fontSize: "0.85rem" }} onClick={fetchQuotasList}>🔄 Refresh</button>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
                  {quotasList.map(quota => (
                    <div key={quota.id} style={{ padding: "1.2rem", background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-premium)", opacity: quota.is_active ? 1 : 0.6 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
                        <span style={{ fontWeight: 700, color: "var(--text-header)", fontSize: "1.1rem" }}>{quota.id}</span>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>Active</span>
                          <input type="checkbox" checked={quota.is_active} onChange={(e) => handleUpdateQuota(quota.id, quota.max_tokens, quota.reset_period, e.target.checked)} />
                        </div>
                      </div>
                      
                      <div style={{ marginBottom: "1rem" }}>
                         <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: "0.3rem" }}>
                            <span style={{ color: "var(--text-dim)" }}>Tokens Used</span>
                            <span style={{ fontWeight: "bold", color: quota.percent_used > 90 ? "#ef4444" : "var(--accent-primary)" }}>{quota.used_tokens} / {quota.max_tokens}</span>
                         </div>
                         <div style={{ width: "100%", height: "8px", background: "rgba(0,0,0,0.2)", borderRadius: "4px", overflow: "hidden" }}>
                            <div style={{ width: `${Math.min(100, quota.percent_used)}%`, height: "100%", background: quota.percent_used > 90 ? "#ef4444" : "var(--accent-primary)", transition: "width 0.3s ease" }}></div>
                         </div>
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>Max Tokens limit</span>
                          <input type="number" value={quota.max_tokens} onChange={(e) => {
                            const newQuotas = [...quotasList];
                            const q = newQuotas.find(x => x.id === quota.id);
                            q.max_tokens = e.target.value;
                            setQuotasList(newQuotas);
                          }} onBlur={(e) => handleUpdateQuota(quota.id, e.target.value, quota.reset_period, quota.is_active)}
                          style={{ width: "100px", padding: "4px 8px", background: "rgba(0,0,0,0.2)", border: "1px solid var(--glass-border)", borderRadius: "6px", color: "white" }} />
                        </div>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>Reset Period</span>
                          <select value={quota.reset_period} onChange={(e) => handleUpdateQuota(quota.id, quota.max_tokens, e.target.value, quota.is_active)}
                           style={{ padding: "4px 8px", background: "rgba(0,0,0,0.2)", border: "1px solid var(--glass-border)", borderRadius: "6px", color: "white" }}>
                            <option value="daily">Daily</option>
                            <option value="weekly">Weekly</option>
                            <option value="monthly">Monthly</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  ))}
                  
                  {/* Add New Tenant Card placeholder */}
                  <div style={{ padding: "1.2rem", background: "rgba(0,0,0,0.1)", borderRadius: "16px", border: "1px dashed var(--glass-border)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", transition: "all 0.2s ease" }}
                    onMouseEnter={(e) => e.currentTarget.style.borderColor = "var(--accent-primary)"}
                    onMouseLeave={(e) => e.currentTarget.style.borderColor = "var(--glass-border)"}
                    onClick={() => {
                        const newTenant = prompt("Enter new tenant ID:");
                        if (newTenant) {
                            handleUpdateQuota(newTenant, 10000, "daily", true);
                        }
                    }}>
                    <span style={{ color: "var(--accent-primary)", fontWeight: "bold" }}>+ Add Tenant Quota</span>
                  </div>
                </div>
              </div>
            )}

            {/* ── Plugin Configuration Modal ── */}
            {showPluginModal && selectedPlugin && (
              <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.6)", backdropFilter: "blur(8px)", zIndex: 2000, display: "flex", alignItems: "center", justifyContent: "center" }}
                onClick={(e) => { if (e.target === e.currentTarget) setShowPluginModal(false); }}>
                <div style={{ width: "550px", maxHeight: "80vh", overflowY: "auto", background: "var(--bg-deep)", borderRadius: "20px", border: "1px solid var(--glass-border)", padding: "2rem", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
                  <h3 style={{ color: "var(--text-header)", marginBottom: "0.3rem" }}>{selectedPlugin.label}</h3>
                  <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "1.5rem" }}>{selectedPlugin.description}</p>

                  {/* Scope Selector */}
                  <div style={{ marginBottom: "1.2rem" }}>
                    <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.8rem", marginBottom: "0.5rem", fontWeight: 600 }}>Apply To</label>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button onClick={() => setPluginScope("global")} style={{
                        padding: "6px 16px", borderRadius: "8px", border: "1px solid var(--glass-border)",
                        background: pluginScope === "global" ? "var(--accent-primary)" : "transparent",
                        color: pluginScope === "global" ? "white" : "var(--text-dim)", cursor: "pointer", fontSize: "0.85rem"
                      }}>🌍 Global</button>
                      <button onClick={() => setPluginScope("route")} style={{
                        padding: "6px 16px", borderRadius: "8px", border: "1px solid var(--glass-border)",
                        background: pluginScope === "route" ? "var(--accent-primary)" : "transparent",
                        color: pluginScope === "route" ? "white" : "var(--text-dim)", cursor: "pointer", fontSize: "0.85rem"
                      }}>🔀 Specific Route</button>
                    </div>
                    {pluginScope === "route" && (
                      <select className="model-select-dropdown" style={{ width: "100%", padding: "10px", marginTop: "0.5rem", background: "rgba(0,0,0,0.2)" }}
                        value={pluginRouteId} onChange={(e) => setPluginRouteId(e.target.value)}>
                        <option value="">— Select a route —</option>
                        {kongRoutes.map(r => <option key={r.id} value={r.id}>{r.name} ({(r.paths||[]).join(", ")})</option>)}
                      </select>
                    )}
                  </div>

                  {/* Dynamic Fields */}
                  {selectedPlugin.fields.map(field => (
                    <div key={field.key} style={{ marginBottom: "1rem" }}>
                      <label style={{ display: "block", color: "var(--text-dim)", fontSize: "0.8rem", marginBottom: "0.4rem", fontWeight: 600 }}>
                        {field.label}{field.required && <span style={{ color: "#ef4444" }}> *</span>}
                      </label>
                      {field.type === "select" ? (
                        <select className="model-select-dropdown" style={{ width: "100%", padding: "10px", background: "rgba(0,0,0,0.2)" }}
                          value={pluginFormData[field.key] ?? field.default}
                          onChange={(e) => setPluginFormData({...pluginFormData, [field.key]: e.target.value})}>
                          {(field.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : field.type === "boolean" ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <input type="checkbox" checked={pluginFormData[field.key] ?? field.default}
                            onChange={(e) => setPluginFormData({...pluginFormData, [field.key]: e.target.checked})} />
                          <span style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>Enabled</span>
                        </div>
                      ) : (
                        <input type={field.type === "number" ? "number" : "text"} className="model-select-dropdown"
                          style={{ width: "100%", padding: "10px", background: "rgba(0,0,0,0.2)" }}
                          value={pluginFormData[field.key] ?? field.default ?? ""}
                          placeholder={field.hint || ""}
                          onChange={(e) => setPluginFormData({...pluginFormData, [field.key]: e.target.value})} />
                      )}
                    </div>
                  ))}

                  {/* Error alert inside modal */}
                  {error && (
                    <div style={{ padding: "0.8rem", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: "10px", marginBottom: "1rem", fontSize: "0.82rem", color: "#fca5a5", wordBreak: "break-word" }}>
                      ⚠️ {error}
                    </div>
                  )}

                  {/* Actions */}
                  <div style={{ display: "flex", gap: "1rem", marginTop: "1.5rem" }}>
                    <button className="dashboard-btn" style={{ flex: 1, background: "var(--accent-primary)", fontWeight: 600 }}
                      onClick={handleApplyPlugin} disabled={loading}>
                      {loading ? "Applying..." : "✓ Apply Plugin"}
                    </button>
                    <button className="dashboard-btn" style={{ flex: 1 }}
                      onClick={() => setShowPluginModal(false)}>Cancel</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── OBSERVABILITY TAB ── */}
        {activeTab === "observability" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button onClick={() => setObservabilitySubTab("kong")} style={{
                padding: "8px 16px", borderRadius: "10px", border: observabilitySubTab === "kong" ? "1px solid #3b82f6" : "1px solid var(--glass-border)",
                background: observabilitySubTab === "kong" ? "rgba(59, 130, 246, 0.15)" : "var(--bg-card)",
                color: observabilitySubTab === "kong" ? "#60a5fa" : "var(--text-dim)", cursor: "pointer", fontWeight: observabilitySubTab === "kong" ? "bold" : "normal"
              }}>🌍 Kong Edge Metrics</button>
              <button onClick={() => setObservabilitySubTab("fastapi")} style={{
                padding: "8px 16px", borderRadius: "10px", border: observabilitySubTab === "fastapi" ? "1px solid #3b82f6" : "1px solid var(--glass-border)",
                background: observabilitySubTab === "fastapi" ? "rgba(59, 130, 246, 0.15)" : "var(--bg-card)",
                color: observabilitySubTab === "fastapi" ? "#60a5fa" : "var(--text-dim)", cursor: "pointer", fontWeight: observabilitySubTab === "fastapi" ? "bold" : "normal"
              }}>🧠 AI Platform Metrics</button>
              <button onClick={() => setObservabilitySubTab("nextora_bi")} style={{
                padding: "8px 16px", borderRadius: "10px", border: observabilitySubTab === "nextora_bi" ? "1px solid #10b981" : "1px solid var(--glass-border)",
                background: observabilitySubTab === "nextora_bi" ? "rgba(16, 185, 129, 0.15)" : "var(--bg-card)",
                color: observabilitySubTab === "nextora_bi" ? "#34d399" : "var(--text-dim)", cursor: "pointer", fontWeight: observabilitySubTab === "nextora_bi" ? "bold" : "normal"
              }}>💹 Business Analytics</button>
            </div>
            <div style={{ background: "var(--bg-card)", borderRadius: "16px", border: "1px solid var(--glass-border)", overflow: "hidden", height: "800px" }}>
              {observabilitySubTab === "kong" && (
                <iframe src="http://localhost:3001/d/mY9p7dQmz?orgId=1&kiosk=tv&theme=dark" width="100%" height="100%" frameBorder="0" style={{ display: "block" }}></iframe>
              )}
              {observabilitySubTab === "fastapi" && (
                <iframe src="http://localhost:3001/d/2SEsuEZ4k?orgId=1&kiosk=tv&theme=dark" width="100%" height="100%" frameBorder="0" style={{ display: "block" }}></iframe>
              )}
              {observabilitySubTab === "nextora_bi" && (
                <iframe src="http://localhost:3001/d/nextora_bi_dashboard?orgId=1&kiosk=tv&theme=dark" width="100%" height="100%" frameBorder="0" style={{ display: "block" }}></iframe>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminPortal;
