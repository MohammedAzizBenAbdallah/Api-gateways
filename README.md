# Keycloak & Kong API Gateway Demo

This project demonstrates a full-stack architecture integrated with **Keycloak** for Identity Management and **Kong** as an API Gateway.

## Architecture

- **Frontend**: React (Vite)
- **Backend**: Node.js (Express)
- **API Gateway**: Kong (DB-less mode)
- **Identity Provider**: Keycloak
- **Database**: PostgreSQL (for Keycloak)

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Node.js](https://nodejs.org/) (optional, for local development)

## Getting Started

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd apiGatewayDemo
   ```

2. **Setup Environment Variables**:
   - Copy `backend/.env.example` to `backend/.env`
   - Copy `frontend/.env.example` to `frontend/.env`

3. **Start the containers**:
   ```bash
   docker-compose up -d
   ```

4. **Access the applications**:
   - **Frontend**: [http://localhost:5173](http://localhost:5173)
   - **Keycloak Admin**: [http://localhost:8080](http://localhost:8080) (Admin: `admin` / `admin`)
   - **Kong Proxy**: [http://localhost:8000](http://localhost:8000)
   - **Kong Admin API**: [http://localhost:8001](http://localhost:8001)

## Key Features

- **JWT Authentication**: Kong validates JWT tokens issued by Keycloak before forwarding requests to the backend.
- **Role-Based Access Control**: Backend routes are protected based on Keycloak roles (`admin`, `user`).
- **Automated Realm Import**: Keycloak automatically imports the demo realm configuration on startup.

## Testing the Flow

1. Log in to the Frontend using the provided demo users in the Keycloak realm.
2. Click **"Fetch Documents"**. The request will:
   - Go to `localhost:5173` (Frontend)
   - Call the Proxy at `localhost:8000/api/documents` (Kong)
   - Kong validates the JWT with Keycloak.
   - Kong forwards the request to `backend:5000/documents`.
