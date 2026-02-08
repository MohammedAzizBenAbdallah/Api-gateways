import { createContext, useEffect, useState, useRef } from "react";
import Keycloak from "keycloak-js";

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [isLogin, setIsLogin] = useState(false);
    const [token, setToken] = useState(null);
    const isRun = useRef(false);
    const clientRef = useRef(null);

    useEffect(() => {
        if (isRun.current) return;
        isRun.current = true;

        const client = new Keycloak({
            url: import.meta.env.VITE_KEYCLOAK_URL,
            realm: import.meta.env.VITE_KEYCLOAK_REALM,
            clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID
        });
        clientRef.current = client;

        client.init({
            onLoad: "login-required",
            checkLoginIframe: false
        }).then((authenticated) => {
            setIsLogin(authenticated);
            setToken(client.token);
        }).catch(err => {
            console.error("Keycloak init failed:", err);
        });
    }, []);

    const logout = () => {
        if (clientRef.current) {
            clientRef.current.logout();
        }
    };

    return (
        <AuthContext.Provider value={{ isLogin, token, logout }}>
            {children}
        </AuthContext.Provider>
    );
};
