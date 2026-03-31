import { useEffect, useRef, useState } from "react";
import useAuth from "../hooks/useAuth";
import axios from "axios";
import AIChat from "./AIChat";

export default function Protected() {
  const { logout, token } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState(null);
  const [systemInfo, setSystemInfo] = useState(null);
  const [loading, setLoading] = useState(false);

  console.log(token);

  const fetchAdmin = async () => {
    setError(null);
    setSystemInfo(null);
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
    setSystemInfo(null);
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

  const fetchNextora = async () => {
    setError(null);
    setSystemInfo(null);
    setLoading(true);
    try {
      const config = {
        headers: {
          authorization: `Bearer ${token}`
        },
      };
      // Directly hit the Nextora route on the local gateway 
      await axios.get("http://localhost:8000/nextora", config);
      setSystemInfo("✅ Nextora Zero-Trust Connection Successful! (HTML entry point received)");
    } catch (err) {
      if (err.response?.status === 403) {
        setError("Nextora access blocked by Gateway (403)");
      } else if (err.response?.status === 401) {
        setError("Nextora access unauthorized (401)");
      } else {
        setError("Network error connecting to Nextora via Gateway");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AIChat
      logout={logout}
      fetchAdmin={fetchAdmin}
      fetchDocuments={fetchDocuments}
      fetchNextora={fetchNextora}
      loading={loading}
      error={error}
      systemInfo={systemInfo}
      documents={documents}
    />
  );
}
