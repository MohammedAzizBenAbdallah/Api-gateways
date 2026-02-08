import { useEffect, useRef, useState } from "react"
import useAuth from "../hooks/useAuth"
import axios from "axios"

export default function Protected() {
    const { logout, token } = useAuth()
    const [documents, setDocuments] = useState([])
    const [error, setError] = useState(null)
    const [loading, setLoading] = useState(false)

    const fetchAdmin = async () => {
        setError(null)
        setLoading(true)

        try {
            const config = {
                headers: {
                    authorization: `Bearer ${token}`
                }
            }

            const res = await axios.get("/api/admin", config)
            setDocuments(res.data.data)
        } catch (err) {
            // Better error messages based on status code
            if (err.response) {
                switch (err.response.status) {
                    case 403:
                        setError("Access denied. You don't have permission to view this.")
                        break
                    case 401:
                        setError("Your session has expired. Please login again.")
                        break
                    case 404:
                        setError("Resource not found.")
                        break
                    case 500:
                        setError("Server error. Please try again later.")
                        break
                    default:
                        setError(err.response.data?.message || "Something went wrong.")
                }
            } else if (err.request) {
                setError("Network error. Please check your connection.")
            } else {
                setError(err.message)
            }
        } finally {
            setLoading(false)
        }
    }

    const fetchDocuments = async () => {
        setError(null)
        setLoading(true)

        try {
            const config = {
                headers: {
                    authorization: `Bearer ${token}`
                }
            }

            const res = await axios.get("/api/documents", config)
            setDocuments(res.data.data)
        } catch (err) {
            if (err.response) {
                switch (err.response.status) {
                    case 403:
                        setError("Access denied. You don't have permission to view documents.")
                        break
                    case 401:
                        setError("Your session has expired. Please login again.")
                        break
                    default:
                        setError(err.response.data?.message || "Failed to fetch documents.")
                }
            } else if (err.request) {
                setError("Network error. Please check your connection.")
            } else {
                setError(err.message)
            }
        } finally {
            setLoading(false)
        }
    }

    return (
        <div>
            <h1>I love latinas</h1>
            {console.log(token)}
            <div>
                <button onClick={logout}>Logout</button>
                <button onClick={fetchAdmin} disabled={loading}>
                    {loading ? "Loading..." : "Fetch Admin"}
                </button>
                <button onClick={fetchDocuments} disabled={loading}>
                    {loading ? "Loading..." : "Fetch Documents"}
                </button>
            </div>

            {loading && <p>Loading...</p>}

            {error && (
                <div style={{
                    color: "red",
                    padding: "10px",
                    border: "1px solid red",
                    borderRadius: "5px",
                    margin: "10px 0",
                    backgroundColor: "#ffebee"
                }}>
                    <strong>Error:</strong> {error}
                </div>
            )}

            {!error && !loading && documents.length > 0 && (
                <ul>
                    {documents.map(doc => (
                        <li key={doc.id}>{doc.name}</li>
                    ))}
                </ul>
            )}

            {!error && !loading && documents.length === 0 && (
                <p>No documents to display.</p>
            )}
        </div>
    )
}