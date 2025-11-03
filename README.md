# x402 Payment Gateway

Multi-chain payment verification for HTTP 402 Payment Required.

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Quick Start

```bash
git clone https://github.com/mizuki-tamaki/kamiyo-payai.git
cd kamiyo-payai
cp .env.example .env
# Edit .env with your configuration
docker-compose up -d
docker-compose exec x402-api alembic upgrade head
```

API available at `http://localhost:8000`
Documentation at `http://localhost:8000/docs`

## Features

- PayAI network integration with direct on-chain fallback
- Multi-chain support: Base, Polygon, Avalanche, Solana, Sei, IoTeX, Peaq
- Real-time payment verification and analytics
- Risk scoring with configurable thresholds
- Redis caching for performance
- Prometheus metrics and Grafana dashboards
- Celery background workers for cleanup and aggregation

## Architecture

Client sends payment proof via headers:
- `X-PAYMENT` - PayAI network token
- `x-payment-tx` + `x-payment-chain` - Direct on-chain transaction

Gateway verifies payment and grants access to protected endpoints.

## Configuration

Required environment variables:

```bash
X402_PAYAI_MERCHANT_ADDRESS=0xYourAddress
X402_BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/KEY
X402_ADMIN_KEY=<secure-random-key>
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db
REDIS_URL=redis://localhost:6379/0
```

See `.env.example` for full configuration.

## API Usage

### Request Protected Resource

```bash
curl http://localhost:8000/exploits
```

Response (402):
```json
{
  "error": "Payment required",
  "price": "0.01",
  "merchant": "0x...",
  "paymentOptions": [...]
}
```

### Verify Payment

```bash
curl -X POST http://localhost:8000/x402/verify-payment \
  -H "Content-Type: application/json" \
  -d '{"tx_hash": "0x...", "chain": "base", "expected_amount": 0.01}'
```

### Access with Payment

```bash
curl http://localhost:8000/exploits \
  -H "x-payment-tx: 0x..." \
  -H "x-payment-chain: base"
```

## Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload
```

Run tests:
```bash
pytest tests/ -v --cov=api
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment guide.

Key requirements:
- PostgreSQL 15+
- Redis 7+
- Secure RPC endpoints (Alchemy/Infura)
- SSL/TLS certificate
- Firewall configuration

## Monitoring

- Prometheus metrics: `http://localhost:9090`
- Grafana dashboards: `http://localhost:3000`
- Celery monitoring: `http://localhost:5555`

## License

AGPL-3.0 with commercial use restriction.
Commercial licensing: licensing@kamiyo.ai

## Support

- Issues: https://github.com/mizuki-tamaki/kamiyo-payai/issues
- Email: dev@kamiyo.ai
- Security: security@kamiyo.ai
