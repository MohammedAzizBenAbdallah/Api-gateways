import { useEffect, useRef, useState } from "react";
import useAuth from "../hooks/useAuth";
import axios from "axios";
import AIChat from "./AIChat";

export default function Protected() {
  const { logout, token } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  console.log(token);

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
    <AIChat
      logout={logout}
      fetchAdmin={fetchAdmin}
      fetchDocuments={fetchDocuments}
      loading={loading}
      error={error}
      documents={documents}
    />
  );
}
