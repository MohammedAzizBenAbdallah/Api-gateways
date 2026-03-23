const express = require("express")
const app = express()

app.get("/", (req: any, res: any) => {
    res.send("Hello World!")
})

app.listen(8002, () => {
    console.log("Server is running on port 8002")
})