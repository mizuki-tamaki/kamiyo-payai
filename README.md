# x402 Payment Gateway

Multi-chain payment verification for HTTP 402 Payment Required.

```
┌─────────┐     402      ┌──────────────┐     verify     ┌───────────┐
│ Client  │ ──────────> │ x402Gateway  │ ────────────> │ Blockchain │
└─────────┘              └──────────────┘                └───────────┘
     │                          │
     │ pay + retry              │ 200 OK
     └─────────────────────────>│
```

## Features

- **PayAI Network Integration**: Instant payment verification via facilitator
- **Direct On-Chain Fallback**: Automatic fallback to RPC verification
- **Multi-Chain Support**: 12 networks including Solana, Base, Polygon
- **Real-Time Analytics**: Track payment success rates and revenue
- **Production Ready**: Comprehensive tests, error handling, monitoring

## Quick Start

```bash
git clone https://github.com/mizuki-tamaki/kamiyo-payai.git
cd kamiyo-payai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
```bash
X402_PAYAI_ENABLED=true
X402_PAYAI_MERCHANT_ADDRESS=0xYourAddress
X402_BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
X402_ENDPOINT_PRICES=/exploits:0.01,/api/analysis:0.02
```

Run server:
```bash
uvicorn api.main:app --reload
```

## Usage

### Payment Flow

1. Client requests protected endpoint
2. Server returns 402 with payment options
3. Client authorizes payment (PayAI or direct transfer)
4. Client retries request with payment proof
5. Server verifies and grants access

### Example: Python Client

```python
import httpx

response = httpx.get("https://api.example.com/exploits")

if response.status_code == 402:
    payment_data = response.json()
    # Option 1: PayAI Network
    token = authorize_payai(payment_data)
    response = httpx.get(
        "https://api.example.com/exploits",
        headers={"X-PAYMENT": token}
    )
    
    # Option 2: Direct on-chain
    tx_hash = send_usdc(payment_data["merchant"], payment_data["amount"])
    response = httpx.get(
        "https://api.example.com/exploits",
        headers={
            "x-payment-tx": tx_hash,
            "x-payment-chain": "base"
        }
    )

print(response.json())
```

### Example: cURL

```bash
# Get payment requirements
curl https://api.example.com/exploits

# Response:
# {
#   "error": "Payment required",
#   "price": "0.01",
#   "merchant": "0x...",
#   "paymentOptions": [...]
# }

# Pay and retry
curl https://api.example.com/exploits \
  -H "x-payment-tx: 0xabc..." \
  -H "x-payment-chain: base"
```

## API

### Protected Endpoints

Configure pricing in `.env`:
```bash
X402_ENDPOINT_PRICES=/exploits:0.01,/api/analysis:0.02
```

### Payment Headers

**PayAI Network:**
```
X-PAYMENT: <base64-encoded-payment-token>
```

**Direct On-Chain:**
```
x-payment-tx: <transaction-hash>
x-payment-chain: <network-name>
```

### Supported Chains

| Chain      | Token | Network Name |
|------------|-------|--------------|
| Base       | USDC  | `base`       |
| Polygon    | USDC  | `polygon`    |
| Avalanche  | USDC  | `avalanche`  |
| Solana     | USDC  | `solana`     |
| Sei        | USDC  | `sei`        |
| IoTeX      | USDC  | `iotex`      |
| Peaq       | USDC  | `peaq`       |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    HTTP Middleware                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │ X402Middleware: Intercept requests, check payment  │  │
│  └────────────────────┬───────────────────────────────┘  │
└───────────────────────┼──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│              UnifiedPaymentGateway                        │
│  ┌─────────────────┐          ┌────────────────────┐     │
│  │ PayAI Facilitator│          │ Direct On-Chain   │     │
│  │  (Priority 1)   │          │   (Priority 2)     │     │
│  │                 │          │                    │     │
│  │ - Fast verify   │          │ - RPC queries      │     │
│  │ - Instant       │          │ - Blockchain read  │     │
│  │ - Fallback auto │          │ - Always available │     │
│  └─────────────────┘          └────────────────────┘     │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│                  Payment Analytics                        │
│  - Success rates                                          │
│  - Verification latency                                   │
│  - Revenue tracking                                       │
│  - Facilitator performance                                │
└──────────────────────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design.

## Testing

```bash
# Run all tests
pytest api/x402/tests/ -v

# Run specific test
pytest api/x402/tests/test_payment_gateway.py::test_payai_success -v

# With coverage
pytest api/x402/tests/ --cov=api/x402 --cov-report=html
```

All tests passing (31/31).

## Configuration

### Required Environment Variables

```bash
# Enable PayAI Network integration
X402_PAYAI_ENABLED=true

# Merchant receiving address
X402_PAYAI_MERCHANT_ADDRESS=0x8595171C4A3d5B9F70585c4AbAAd08613360e643

# PayAI facilitator endpoint
X402_PAYAI_FACILITATOR_URL=https://facilitator.payai.network

# Enable unified gateway (PayAI + direct fallback)
X402_USE_UNIFIED_GATEWAY=true

# RPC endpoints for on-chain verification
X402_BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
X402_POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
X402_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Endpoint pricing (CSV format)
X402_ENDPOINT_PRICES=/exploits:0.01,/api/v2/analysis:0.02
```

### Optional Environment Variables

```bash
# Database connection
DATABASE_URL=postgresql://user:pass@localhost/db

# Payment age limit (seconds)
X402_MAX_PAYMENT_AGE=604800

# Minimum payment amount (USD)
X402_MIN_PAYMENT_AMOUNT=0.10
```

## Production Deployment

### Database Setup

```bash
psql -U postgres < database/schema.sql
```

### Run with Gunicorn

```bash
gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

### Environment Variables

Set all required environment variables in production:
- Use dedicated RPC endpoints with SLAs
- Monitor PayAI facilitator availability
- Enable payment analytics for revenue tracking

### Security

- Never commit `.env` files
- Use read-only RPC endpoints
- Enable rate limiting
- Monitor failed payment attempts

See [SECURITY.md](SECURITY.md) for security policy.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Documentation

- [Architecture](ARCHITECTURE.md) - System design and flow diagrams
- [Security](SECURITY.md) - Security policy and best practices
- [Contributing](CONTRIBUTING.md) - Development setup and guidelines

## License

AGPL-3.0 with commercial use restriction.

This software may not be used for commercial purposes without explicit written permission. For commercial licensing, contact: licensing@kamiyo.ai

See [LICENSE](LICENSE) for full terms.

## Support

- Issues: [GitHub Issues](https://github.com/mizuki-tamaki/kamiyo-payai/issues)
- Email: dev@kamiyo.ai
- Security: security@kamiyo.ai
