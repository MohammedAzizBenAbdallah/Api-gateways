import { createContext, useEffect, useState, useRef } from "react";
import Keycloak from "keycloak-js";

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [isLogin, setIsLogin] = useState(false);
    const [token, setToken] = useState(null);
    const [roles, setRoles] = useState([]);
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

        // redirectUri tells Keycloak where to send the browser after login.
        // Use VITE_APP_URL (the Kong gateway) so the flow goes through Kong,
        // not the raw Vite dev server. Falls back to current origin if not set.
        const redirectUri = import.meta.env.VITE_APP_URL
            ? import.meta.env.VITE_APP_URL + '/'
            : window.location.origin + '/';

        client.init({
            onLoad: "login-required",
            checkLoginIframe: false,
            redirectUri
        }).then((authenticated) => {
            setIsLogin(authenticated);
            setToken(client.token);
            setRoles(client.realmAccess?.roles || []);
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
        <AuthContext.Provider value={{ isLogin, token, roles, logout }}>
            {children}
        </AuthContext.Provider>
    );
};
