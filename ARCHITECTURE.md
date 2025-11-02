# Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         HTTP Client                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ GET /exploits
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                      X402Middleware                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Check payment headers                             │   │
│  │ 2. Route to UnifiedPaymentGateway                    │   │
│  │ 3. Return 402 if no valid payment                    │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ Payment verification
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                  UnifiedPaymentGateway                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Priority Routing                        │   │
│  │                                                       │   │
│  │  Priority 1: PayAI Facilitator                       │   │
│  │  ├─ Base64 decode payment token                      │   │
│  │  ├─ Verify signature                                 │   │
│  │  └─ Check amount/merchant                            │   │
│  │                                                       │   │
│  │  Priority 2: Direct On-Chain                         │   │
│  │  ├─ Extract tx hash + chain                          │   │
│  │  ├─ Query RPC endpoint                               │   │
│  │  └─ Verify transfer to merchant                      │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ Record metrics
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   PaymentAnalytics                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - Track verification attempts                        │   │
│  │ - Record success/failure rates                       │   │
│  │ - Monitor facilitator performance                    │   │
│  │ - Calculate revenue metrics                          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Payment Flow

### Successful Payment

```
Client                  Server                 PayAI              Blockchain
  │                        │                     │                    │
  │  GET /exploits         │                     │                    │
  ├───────────────────────>│                     │                    │
  │                        │                     │                    │
  │  402 Payment Required  │                     │                    │
  │<───────────────────────┤                     │                    │
  │  {paymentOptions:[]}   │                     │                    │
  │                        │                     │                    │
  │  Authorize payment     │                     │                    │
  ├────────────────────────┼────────────────────>│                    │
  │                        │                     │                    │
  │  Payment token         │                     │  Submit tx         │
  │<────────────────────────┼─────────────────────┤──────────────────>│
  │                        │                     │                    │
  │  GET /exploits         │                     │                    │
  │  X-PAYMENT: token      │                     │                    │
  ├───────────────────────>│                     │                    │
  │                        │  Verify token       │                    │
  │                        ├────────────────────>│                    │
  │                        │  Valid ✓            │                    │
  │                        │<────────────────────┤                    │
  │                        │                     │                    │
  │  200 OK                │                     │                    │
  │  {data:[...]}          │                     │                    │
  │<───────────────────────┤                     │                    │
```

### Fallback to Direct Verification

```
Client                  Server                 Blockchain
  │                        │                        │
  │  GET /exploits         │                        │
  │  x-payment-tx: 0xabc   │                        │
  │  x-payment-chain: base │                        │
  ├───────────────────────>│                        │
  │                        │  Query transaction     │
  │                        ├───────────────────────>│
  │                        │                        │
  │                        │  {to, value, block}    │
  │                        │<───────────────────────┤
  │                        │                        │
  │                        │  Verify:               │
  │                        │  - to == merchant      │
  │                        │  - value >= price      │
  │                        │  - age < 7 days        │
  │                        │                        │
  │  200 OK                │                        │
  │<───────────────────────┤                        │
```

## Supported Chains

### EVM-Compatible
- Base (USDC)
- Polygon (USDC)
- Avalanche (USDC)
- Sei (USDC)
- IoTeX (USDC)
- Peaq (USDC)

### Solana
- Mainnet (USDC SPL token)

## Configuration

### Environment Variables

```
X402_PAYAI_ENABLED=true|false
X402_PAYAI_MERCHANT_ADDRESS=0x...
X402_PAYAI_FACILITATOR_URL=https://facilitator.payai.network
X402_USE_UNIFIED_GATEWAY=true|false

# RPC endpoints per chain
X402_BASE_RPC_URL=https://...
X402_POLYGON_RPC_URL=https://...
X402_SOLANA_RPC_URL=https://...

# Pricing per endpoint
X402_ENDPOINT_PRICES=/path:0.01,/other:0.02
```

### Pricing Configuration

Endpoint prices defined as CSV:
```
/exploits:0.01
/exploits/latest-alert:0.01
/api/v2/analysis/deep-dive:0.02
```

Parsed on startup, cached in memory.

## Database Schema

### payments table

```sql
CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    chain VARCHAR(20) NOT NULL,
    from_address VARCHAR(66) NOT NULL,
    amount DECIMAL(20,6) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    verified_at TIMESTAMP DEFAULT NOW(),
    facilitator VARCHAR(20) DEFAULT 'direct'
);
```

### payment_analytics table

```sql
CREATE TABLE payment_analytics (
    id SERIAL PRIMARY KEY,
    endpoint VARCHAR(255) NOT NULL,
    facilitator VARCHAR(20) NOT NULL,
    success BOOLEAN NOT NULL,
    response_time_ms INTEGER,
    error_message TEXT,
    recorded_at TIMESTAMP DEFAULT NOW()
);
```

## Error Handling

### PayAI Facilitator Unavailable
- Automatically falls back to direct on-chain verification
- Logs facilitator downtime
- No impact on payment acceptance

### RPC Endpoint Failure
- Returns 402 with retry-after header
- Logs RPC errors for monitoring
- Client can retry or use different payment method

### Invalid Payment
- Returns 402 with error details
- Tracks failed attempts in analytics
- Rate limits repeated failures

## Security

### Payment Replay Prevention
- Transaction hash stored in database
- Duplicate payment attempts rejected
- Age validation (max 7 days old)

### Amount Verification
- Minimum threshold: $0.10 USD
- Compares payment amount to endpoint price
- Rejects underpayments

### Merchant Address Validation
- All payments must go to configured merchant address
- Prevents payment interception
- Validated on both PayAI and direct verification

## Performance

### Caching
- Endpoint prices cached in memory
- RPC responses cached for duplicate checks
- Payment verification results cached (1 hour TTL)

### Optimization
- Parallel RPC queries for multi-chain support
- Connection pooling for database
- Async HTTP client for PayAI facilitator

### Metrics
- Payment verification latency
- Facilitator success rate
- Revenue per endpoint
- Cache hit rates
