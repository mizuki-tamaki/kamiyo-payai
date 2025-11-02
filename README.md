# x402 Payment Gateway

Multi-chain payment verification for HTTP 402 Payment Required.

## Features

- PayAI Network facilitator integration
- Direct on-chain verification fallback
- 12 blockchain networks supported
- Real-time payment analytics

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload
```

## Configuration

```bash
X402_PAYAI_ENABLED=true
X402_PAYAI_MERCHANT_ADDRESS=0xYourAddress
X402_BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/KEY
```

## API

Protected endpoints return 402 with payment details. Include payment proof in retry.

## Testing

```bash
pytest api/x402/tests/ -v
```

## License

AGPL-3.0
