import axios from "axios";
import { useEffect, useState } from "react";
import useAuth from "./useAuth";

export default function useIntent() {
  const [intents, setIntents] = useState([]);
  const { token } = useAuth();
  useEffect(
    function () {
      async function fetchIntents() {
        if (!token) return;
        const res = await axios.get("/api/admin/intent-mappings", {
          headers: { Authorization: `Bearer ${token}`, "kong-header": "true" },
        });

        setIntents(res.data);
      }
      fetchIntents();
    },
    [token],
  );

  return { intents };
}
