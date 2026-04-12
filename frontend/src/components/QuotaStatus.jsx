import { useEffect, useState } from "react";
import axios from "axios";

const QuotaStatus = ({ token, trigger, pushedData }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = async () => {
    try {
      const config = {
        headers: {
          authorization: `Bearer ${token}`,
          "kong-header": "true",
        },
      };
      const res = await axios.get("/api/governance/quota-status", config);
      setStatus(res.data);
    } catch (err) {
      console.error("Failed to fetch quota status", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (pushedData) {
      setStatus(pushedData);
      setLoading(false);
    } else {
      fetchStatus();
    }
    // Refresh every 30 seconds
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [token, trigger, pushedData]);

  if (loading || !status) return <div className="quota-skeleton" />;

  const { used_tokens, max_tokens, remaining_tokens, percent_used } = status;
  
  // Color logic based on usage
  let statusColor = "#4ade80"; // Green
  if (percent_used > 70) statusColor = "#facc15"; // Yellow
  if (percent_used > 90) statusColor = "#f87171"; // Red

  return (
    <div className="quota-widget">
      <div className="quota-info">
        <span className="quota-label">Daily Tokens</span>
        <span className="quota-value" style={{ color: statusColor }}>
          {remaining_tokens.toLocaleString()} left
        </span>
      </div>
      <div className="quota-progress-container">
        <div 
          className="quota-progress-bar" 
          style={{ 
            width: `${Math.min(100, percent_used)}%`,
            backgroundColor: statusColor 
          }} 
        />
      </div>
      <div className="quota-footer">
        {used_tokens.toLocaleString()} / {max_tokens.toLocaleString()} used
      </div>

      <style>{`
        .quota-widget {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--glass-border);
          border-radius: 12px;
          padding: 0.8rem;
          min-width: 180px;
          backdrop-filter: blur(10px);
          font-family: inherit;
        }
        .quota-info {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.5rem;
        }
        .quota-label {
          font-size: 0.7rem;
          color: var(--text-dim);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .quota-value {
          font-size: 0.8rem;
          font-weight: 600;
        }
        .quota-progress-container {
          height: 6px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 999px;
          overflow: hidden;
          margin-bottom: 0.4rem;
        }
        .quota-progress-bar {
          height: 100%;
          border-radius: 999px;
          transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .quota-footer {
          font-size: 0.65rem;
          color: var(--text-dim);
          text-align: right;
          opacity: 0.7;
        }
        .quota-skeleton {
          height: 50px;
          width: 180px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
          0% { opacity: 0.5; }
          50% { opacity: 1; }
          100% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
};

export default QuotaStatus;
