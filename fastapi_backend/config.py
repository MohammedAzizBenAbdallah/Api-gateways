import os
from dotenv import load_dotenv

load_dotenv()

# Copy .env from parent if it exists or use the one in current dir
# Assuming .env is in the root of the project
DATABASE_URL = os.getenv("PLATFORM_DB_URL")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "newRealm")
PORT = int(os.getenv("PORT", 3000))
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://localhost:5173")
