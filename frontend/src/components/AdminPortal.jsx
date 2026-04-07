import { useState, useEffect } from "react";
import axios from "axios";
import useIntent from "../hooks/useIntent";

const AdminPortal = ({ token, onClose }) => {
  const [activeTab, setActiveTab] = useState("mappings"); // "mappings", "services"
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingMapping, setEditingMapping] = useState(null);

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
    }
  }, [activeTab]);

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
      if (editingMapping) {
        await axios.put(
          `/api/admin/intent-mappings/${editingMapping.id}`,
          formData,
          {
            headers: {
              Authorization: `Bearer ${token}`,
              "kong-header": "true",
            },
          },
        );
      } else {
        await axios.post("/api/admin/intent-mappings", formData, {
          headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
        });
      }
      setShowForm(false);
      setEditingMapping(null);
      fetchMappings();
    } catch (err) {
      setError(err.response?.data?.detail || "Save failed");
    } finally {
      setLoading(false);
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
          width: "90%",
          maxWidth: "800px",
          maxHeight: "80vh",
          background: "var(--bg-card)",
          border: "1px solid var(--glass-border)",
          borderRadius: "24px",
          padding: "2rem",
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
            background: "none",
            border: "none",
            color: "var(--text-dim)",
            cursor: "pointer",
            fontSize: "1.2rem",
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
                : "AI Service Governance"}
            </h2>
            <p style={{ color: "var(--text-dim)", fontSize: "0.9rem" }}>
              {activeTab === "mappings"
                ? "Manage intent-to-service orchestration"
                : "Classify services for security policy enforcement"}
            </p>
          </div>
          {activeTab === "mappings" && (
            <div style={{ display: "flex", gap: "1rem" }}>
              <button className="dashboard-btn" onClick={handleReload}>
                Reload Cache
              </button>
              <button
                className="dashboard-btn"
                style={{ background: "var(--accent-primary)" }}
                onClick={() => {
                  setEditingMapping(null);
                  setFormData({
                    intent_name: "",
                    service_id: "",
                    taxonomy_version: "1.0.0",
                    is_active: true,
                  });
                  setShowForm(true);
                }}
              >
                + Add Mapping
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
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
              }}
            >
              <div>
                <label
                  style={{
                    display: "block",
                    color: "var(--text-dim)",
                    fontSize: "0.85rem",
                    marginBottom: "0.5rem",
                  }}
                >
                  Intent Name
                </label>
                <input
                  className="model-select-dropdown"
                  style={{
                    width: "100%",
                    padding: "12px",
                    background: "rgba(0,0,0,0.2)",
                  }}
                  value={formData.intent_name}
                  onChange={(e) =>
                    setFormData({ ...formData, intent_name: e.target.value })
                  }
                  disabled={!!editingMapping}
                  placeholder="e.g. general_chat"
                  required
                />
              </div>
              <div>
                <label
                  style={{
                    display: "block",
                    color: "var(--text-dim)",
                    fontSize: "0.85rem",
                    marginBottom: "0.5rem",
                  }}
                >
                  Service ID
                </label>
                <input
                  className="model-select-dropdown"
                  style={{
                    width: "100%",
                    padding: "12px",
                    background: "rgba(0,0,0,0.2)",
                  }}
                  value={formData.service_id}
                  onChange={(e) =>
                    setFormData({ ...formData, service_id: e.target.value })
                  }
                  placeholder="e.g. ollama_llama3.2"
                  required
                />
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
              }}
            >
              <div>
                <label
                  style={{
                    display: "block",
                    color: "var(--text-dim)",
                    fontSize: "0.85rem",
                    marginBottom: "0.5rem",
                  }}
                >
                  Taxonomy Version
                </label>
                <input
                  className="model-select-dropdown"
                  style={{
                    width: "100%",
                    padding: "12px",
                    background: "rgba(0,0,0,0.2)",
                  }}
                  value={formData.taxonomy_version}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      taxonomy_version: e.target.value,
                    })
                  }
                />
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-end",
                  gap: "1rem",
                  paddingBottom: "10px",
                }}
              >
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) =>
                    setFormData({ ...formData, is_active: e.target.checked })
                  }
                />
                <label style={{ color: "white" }}>Active</label>
              </div>
            </div>
            <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
              <button
                type="submit"
                className="dashboard-btn"
                style={{ flex: 1, background: "var(--accent-primary)" }}
              >
                {editingMapping ? "Update" : "Create"}
              </button>
              <button
                type="button"
                className="dashboard-btn"
                style={{ flex: 1 }}
                onClick={() => setShowForm(false)}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : activeTab === "mappings" ? (
          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}
          >
            {mappings.map((m) => (
              <div
                key={m.id}
                style={{
                  padding: "1rem",
                  background: "rgba(255,255,255,0.03)",
                  borderRadius: "16px",
                  border: "1px solid var(--glass-border)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.8rem",
                    }}
                  >
                    <span style={{ fontWeight: 600, color: "white" }}>
                      {m.intent_name}
                    </span>
                    <span
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--text-dim)",
                        background: "rgba(255,b255,255,0.05)",
                        padding: "2px 8px",
                        borderRadius: "10px",
                      }}
                    >
                      v{m.taxonomy_version}
                    </span>
                    {!m.is_active && (
                      <span
                        style={{
                          fontSize: "0.7rem",
                          color: "#fca5a5",
                          background: "rgba(239, 68, 68, 0.1)",
                          padding: "2px 8px",
                          borderRadius: "10px",
                        }}
                      >
                        Inactive
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: "0.85rem",
                      color: "var(--text-dim)",
                      marginTop: "0.3rem",
                    }}
                  >
                    Routes to:{" "}
                    <code style={{ color: "var(--accent-primary)" }}>
                      {m.service_id}
                    </code>
                  </div>
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    className="dashboard-btn"
                    style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }}
                    onClick={() => {
                      setEditingMapping(m);
                      setFormData({
                        intent_name: m.intent_name,
                        service_id: m.service_id,
                        taxonomy_version: m.taxonomy_version,
                        is_active: m.is_active,
                      });
                      setShowForm(true);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    className="dashboard-btn"
                    style={{
                      padding: "0.4rem 0.8rem",
                      fontSize: "0.8rem",
                      borderColor: "rgba(239, 68, 68, 0.3)",
                      color: "#fca5a5",
                    }}
                    onClick={() => handleDelete(m.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}
          >
            {services.map((s) => (
              <div
                key={s.service_id}
                style={{
                  padding: "1rem",
                  background: "rgba(255,255,255,0.03)",
                  borderRadius: "16px",
                  border: "1px solid var(--glass-border)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <div
                    style={{
                      fontWeight: 600,
                      color: "white",
                      marginBottom: "0.2rem",
                    }}
                  >
                    {s.service_id}
                  </div>
                  <div
                    style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}
                  >
                    Model:{" "}
                    <span style={{ color: "var(--accent-primary)" }}>
                      {s.model_name}
                    </span>
                  </div>
                </div>
                <div
                  style={{ display: "flex", alignItems: "center", gap: "1rem" }}
                >
                  <div
                    style={{
                      fontSize: "0.75rem",
                      padding: "4px 12px",
                      borderRadius: "20px",
                      background:
                        s.service_type === "cloud"
                          ? "rgba(59, 130, 246, 0.1)"
                          : "rgba(16, 185, 129, 0.1)",
                      color: s.service_type === "cloud" ? "#60a5fa" : "#34d399",
                      border: `1px solid ${s.service_type === "cloud" ? "rgba(59, 130, 246, 0.3)" : "rgba(16, 185, 129, 0.3)"}`,
                    }}
                  >
                    {s.service_type.toUpperCase()}
                  </div>
                  <button
                    className="dashboard-btn"
                    style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }}
                    onClick={() =>
                      toggleServiceType(s.service_id, s.service_type)
                    }
                  >
                    Switch to {s.service_type === "cloud" ? "On-Prem" : "Cloud"}
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
