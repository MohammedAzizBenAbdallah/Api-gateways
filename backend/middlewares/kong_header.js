const kong_header = (req, res, next) => {
    if (req.headers["kong-header"]) {
        next()
    } else {
        res.status(403).json({
            message: "all requests should come from kong gateway"
        })
    }
}

export default kong_header