-- x402 Payment Gateway Database Schema

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    chain VARCHAR(20) NOT NULL,
    from_address VARCHAR(66) NOT NULL,
    to_address VARCHAR(66) NOT NULL,
    amount DECIMAL(20, 6) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    facilitator VARCHAR(20) DEFAULT 'direct',
    verified_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_payments_tx_hash ON payments(tx_hash);
CREATE INDEX idx_payments_chain ON payments(chain);
CREATE INDEX idx_payments_verified_at ON payments(verified_at);

CREATE TABLE IF NOT EXISTS payment_analytics (
    id SERIAL PRIMARY KEY,
    endpoint VARCHAR(255) NOT NULL,
    facilitator VARCHAR(20) NOT NULL,
    success BOOLEAN NOT NULL,
    response_time_ms INTEGER,
    error_message TEXT,
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_analytics_endpoint ON payment_analytics(endpoint);
CREATE INDEX idx_analytics_facilitator ON payment_analytics(facilitator);
CREATE INDEX idx_analytics_recorded_at ON payment_analytics(recorded_at);

-- View for payment statistics
CREATE OR REPLACE VIEW payment_stats AS
SELECT 
    endpoint,
    facilitator,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
    AVG(response_time_ms) as avg_response_time_ms,
    DATE_TRUNC('hour', recorded_at) as hour
FROM payment_analytics
GROUP BY endpoint, facilitator, DATE_TRUNC('hour', recorded_at);

-- View for revenue tracking
CREATE OR REPLACE VIEW revenue_stats AS
SELECT 
    endpoint,
    chain,
    COUNT(*) as payment_count,
    SUM(amount) as total_revenue,
    AVG(amount) as avg_payment,
    DATE_TRUNC('day', verified_at) as day
FROM payments
GROUP BY endpoint, chain, DATE_TRUNC('day', verified_at);
