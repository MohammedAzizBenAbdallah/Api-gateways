async function authorizeAdmin(req, res, next) {
    const roles = req.user.realm_access.roles
    console.log(roles)
    if (roles.includes("admin")) {
        next()
    } else {
        res.status(403).json({
            message: "Forbidden: Insufficient permissions"
        })
    }
}
async function authorizeUser(req, res, next) {
    const roles = req.user.realm_access.roles
    if (roles.includes("user") || roles.includes("admin")) {
        next()
    } else {
        res.status(403).json({
            message: "Forbidden: Insufficient permissions"
        })
    }
}

export { authorizeAdmin, authorizeUser }