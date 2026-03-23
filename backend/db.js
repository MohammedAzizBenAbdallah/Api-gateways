import pg from 'pg';
const { Pool } = pg;

const pool = new Pool({
    connectionString: process.env.PLATFORM_DB_URL,
});

pool.on('error', (err) => {
    console.error('Unexpected error on idle client', err);
    process.exit(-1);
});

export default pool;
