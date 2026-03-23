import jwtmod from "jsonwebtoken";
import jwksClient from "jwks-rsa";

const client = jwksClient({
  jwksUri: `${process.env.KEYCLOAK_URL || "http://localhost:8080"}/realms/${process.env.KEYCLOAK_REALM || "newRealm"}/protocol/openid-connect/certs`,
});

function getKey(header, callback) {
  client.getSigningKey(header.kid, function (err, key) {
    if (err) {
      console.error("JWKS Error:", err.message);
      return callback(err);
    }
    const signingKey = key.getPublicKey();
    callback(null, signingKey);
  });
}

const authenticate = (req, res, next) => {
  console.log(req);
  const authHeader = req.headers["authorization"];
  const token = authHeader && authHeader.split(" ")[1];

  if (!token) {
    return res.status(401).json({
      message: "Unauthorized: No token provided",
    });
  }

  jwtmod.verify(token, getKey, { algorithms: ["RS256"] }, (err, decoded) => {
    if (err) {
      console.error("JWT Verification Error:", err.message);
      return res.status(401).json({
        message: "Unauthorized: Invalid token",
      });
    }
    // console.log("Decoded Token:", decoded)
    // console.log(decoded.realm_access.roles)
    req.user = decoded;
    next();
  });
};

export default authenticate;
