# Contributing

## Development Setup

```bash
git clone https://github.com/mizuki-tamaki/kamiyo-payai.git
cd kamiyo-payai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your RPC endpoints and merchant address.

## Code Style

- PEP 8 compliance
- Type hints required
- Docstrings for public APIs
- Keep functions focused and testable

## Testing

```bash
# Run all tests
pytest api/x402/tests/ -v

# Run specific test
pytest api/x402/tests/test_payment_gateway.py -v

# With coverage
pytest api/x402/tests/ --cov=api/x402 --cov-report=html
```

## Pull Requests

1. Fork and create feature branch
2. Write tests for new functionality
3. Ensure all tests pass
4. Update documentation if needed
5. Submit PR with clear description

## Commit Messages

Use imperative mood:
- `Add PayAI network support`
- `Fix payment verification race condition`
- `Update endpoint pricing logic`

## Architecture

Maintain separation between:
- Payment verification (on-chain)
- Payment tracking (database)
- HTTP middleware (FastAPI)

## License

Contributions accepted under AGPL-3.0. Commercial use requires separate licensing.
