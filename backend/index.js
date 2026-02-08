import dotenv from "dotenv"
dotenv.config()
import cors from "cors"
import express from "express"
import authenticate from "./routes/authenticate.js"
import { authorizeAdmin, authorizeUser } from "./routes/authorize.js"

const app = express()

app.use(cors({
    origin: "http://localhost:5173",
    credentials: true
}))

app.get("/", (req, res) => {
    res.send("Hello World!")
})
app.use(authenticate)
app.use(express.json())

app.get("/documents", authorizeUser, (req, res) => {
    const { email } = req.user;
    console.log(email)
    res.status(200).json({
        message: "Documents",
        client: email,
        data: [
            {
                id: 1,
                name: `${email} user Document 1`
            },
            {
                id: 2,
                name: `${email} user Document 2`
            },
            {
                id: 3,
                name: `${email} user Document 3`
            }
        ]
    })
})

app.get("/admin", authorizeAdmin, (req, res) => {
    const { email } = req.user;
    res.status(200).json({
        message: "admin documents",
        client: email,
        data: [
            {
                id: 1,
                name: `${email} admin Document 1`
            },
            {
                id: 2,
                name: `${email} admin Document 2`
            },
            {
                id: 3,
                name: `${email} admin Document 3`
            }
        ]
    })
})



app.listen(process.env.PORT, () => {
    console.log(`Server is running on port ${process.env.PORT}`)
})