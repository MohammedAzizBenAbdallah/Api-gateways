export default function Public() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: '100vh', width: '100vw', background: 'radial-gradient(circle at center, #1a1a2e 0%, #0f0f1a 100%)',
      color: '#ffffff', fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      <div style={{
        background: 'rgba(255, 255, 255, 0.03)',
        border: '1px solid rgba(255, 255, 255, 0.05)',
        backdropFilter: 'blur(10px)',
        padding: '3rem 4rem',
        borderRadius: '24px',
        textAlign: 'center',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
      }}>
        <div style={{ marginBottom: '2rem' }}>
          <div style={{
            width: '64px', height: '64px', borderRadius: '50%',
            background: 'linear-gradient(135deg, #7c3aed 0%, #3b82f6 100%)',
            margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 30px rgba(124, 58, 237, 0.5)'
           }}>
             <span style={{ fontSize: '24px' }}>✨</span>
          </div>
        </div>
        <h1 style={{ 
          fontSize: '2.5rem', fontWeight: 700, margin: '0 0 1rem 0', letterSpacing: '-0.02em', 
          background: 'linear-gradient(to right, #ffffff, #a5b4fc)', 
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' 
        }}>
          Nextora AI
        </h1>
        <p style={{ color: '#9ca3af', fontSize: '1.1rem', maxWidth: '400px', margin: '0 auto 2.5rem auto', lineHeight: 1.6 }}>
          Secure, Enterprise-Grade AI Orchestration Gateway.
        </p>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'center' }}>
            <div style={{ 
              display: 'flex', alignItems: 'center', gap: '0.8rem', color: '#60a5fa', fontSize: '0.95rem', 
              background: 'rgba(59, 130, 246, 0.1)', padding: '0.75rem 1.5rem', borderRadius: '99px', 
              border: '1px solid rgba(59, 130, 246, 0.2)' 
            }}>
                <span className="spinner" style={{ 
                  width: '18px', height: '18px', border: '2.5px solid rgba(96, 165, 250, 0.3)', 
                  borderTopColor: '#60a5fa', borderRadius: '50%', animation: 'spin 1s linear infinite' 
                }}></span>
                Authenticating Session...
            </div>
            
            <div style={{
              background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '12px', marginTop: '1.5rem',
              border: '1px solid rgba(255,255,255,0.05)'
            }}>
              <p style={{ color: '#9ca3af', fontSize: '0.85rem', margin: 0, maxWidth: '300px', lineHeight: 1.5 }}>
                <strong style={{color: '#facc15'}}>Stuck here?</strong> Ensure you are accessing the platform via <br/>
                <a href="http://197.14.4.163:8000" style={{color: '#60a5fa', textDecoration: 'none', fontWeight: 600}}>http://197.14.4.163:8000</a><br/>
                to bypass strict HTTPS mixed-content blocks.
              </p>
            </div>
        </div>
      </div>
      <style>{`
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}