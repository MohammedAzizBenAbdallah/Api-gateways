import dotenv from "dotenv";
dotenv.config();
import cors from "cors";
import express from "express";
import authenticate from "./routes/authenticate.js";
import morgan from "morgan";
import kong_header from "./middlewares/kong_header.js";
import orchestrator from "./routes/orchestrator.js";

const app = express();

app.use(morgan("dev"));

app.use(
  cors({
    origin: "http://localhost:5173",
    credentials: true,
  }),
);

app.get("/", (req, res) => {
  res.send("hello world!");
});
app.use(kong_header);
app.use(express.json());

// AI Orchestrator Route (Identity verified by Kong)
app.use(authenticate);

app.use("/ai", orchestrator);

app.get("/documents", (req, res) => {
  const { email } = req.user;
  console.log(email);
  res.status(200).json({
    message: "Documents",
    client: email,
    data: [
      {
        id: 1,
        name: `${email} user Document 1`,
      },
      {
        id: 2,
        name: `${email} user Document 2`,
      },
      {
        id: 3,
        name: `${email} user Document 3`,
      },
    ],
  });
});

app.get("/admin", (req, res) => {
  const { email } = req.user;
  res.status(200).json({
    message: "admin documents",
    client: email,
    data: [
      {
        id: 1,
        name: `${email} admin Document 1`,
      },
      {
        id: 2,
        name: `${email} admin Document 2`,
      },
      {
        id: 3,
        name: `${email} admin Document 3`,
      },
    ],
  });
});

app.listen(process.env.PORT, () => {
  console.log(`Server is running on port ${process.env.PORT}`);
});
