import { useEffect, useRef, useState } from "react";
import useAuth from "../hooks/useAuth";
import axios from "axios";
import AIChat from "./AIChat";
import AdminPortal from "./AdminPortal";
import { useKeyPress } from "../../hooks/useKeyPress";

export default function Protected() {
  const { logout, token, roles } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showAdminPortal, setShowAdminPortal] = useState(false);
  useKeyPress("Escape", () => setShowAdminPortal(false));
  const isAdmin = roles.includes("admin");

  const fetchAdmin = async () => {
    setError(null);
    setLoading(true);
    try {
      const config = {
        headers: {
          authorization: `Bearer ${token}`,
          "kong-header": "true",
        },
      };
      const res = await axios.get("/api/admin", config);
      setDocuments(res.data.data);
    } catch (err) {
      setError(
        err.response?.status === 403
          ? "Admin access required"
          : "Network error",
      );
    } finally {
      setLoading(false);
    }
  };

  const fetchDocuments = async () => {
    setError(null);
    setLoading(true);
    try {
      const config = {
        headers: {
          authorization: `Bearer ${token}`,
          "kong-header": "true",
        },
      };
      const res = await axios.get("/api/documents", config);
      setDocuments(res.data.data);
    } catch (err) {
      setError(
        err.response?.status === 403 ? "User access required" : "Network error",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <AIChat
        logout={logout}
        fetchAdmin={fetchAdmin}
        fetchDocuments={fetchDocuments}
        loading={loading}
        error={error}
        documents={documents}
        isAdmin={isAdmin}
        onOpenAdmin={() => setShowAdminPortal(true)}
      />
      {showAdminPortal && (
        <AdminPortal token={token} onClose={() => setShowAdminPortal(false)} />
      )}
    </>
  );
}
