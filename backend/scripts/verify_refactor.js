// Verification script for Tenant Permission Refactor
// Note: This script assumes the backend and platform-db are running.

const BACKEND_URL = "http://localhost:5000";

async function testAccess(tenantId, serviceId, expectedStatus) {
    console.log(`Testing access for Tenant: ${tenantId}, Service: ${serviceId}...`);
    
    // Mocking the headers that Kong would send to the backend
    const response = await fetch(`${BACKEND_URL}/ai/orchestrate/${serviceId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenantId,
            'kong-header': 'true' // Bypass gateway check if testing backend directly
        },
        body: JSON.stringify({
            model: "DeepSeek-Coder:latest",
            messages: [{ role: "user", content: "Hello!" }],
            stream: false
        })
    });

    console.log(`Status: ${response.status}`);
    if (response.status === expectedStatus) {
        console.log("✅ Match");
    } else {
        console.log(`❌ Mismatch (Expected ${expectedStatus})`);
        const body = await response.json();
        console.log("Response Body:", body);
    }
    console.log("---");
}

async function runTests() {
    console.log("Starting Verification Tests...\n");

    // 1. Acme Corp -> Ollama (Authorized in Seed Data)
    await testAccess('acme-corp', 'ollama', 200);

    // 2. Acme Corp -> DeepSeek Cloud (Forbidden in Seed Data)
    await testAccess('acme-corp', 'deepseek-cloud', 403);

    // 3. Globex -> DeepSeek Cloud (Authorized in Seed Data)
    await testAccess('globex', 'deepseek-cloud', 200);

    // 4. Unknown Service
    await testAccess('globex', 'unknown-service', 404);
}

runTests().catch(err => console.error("Test failed:", err));
