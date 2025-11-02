# Security Policy

## Reporting Vulnerabilities

**Email:** security@kamiyo.ai

Do not open public issues for security vulnerabilities.

### What to Include

- Vulnerability description
- Reproduction steps
- Potential impact
- Suggested fix (optional)

### Response Timeline

- Initial response: 48 hours
- Status update: 7 days
- Fix timeline: Varies by severity

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
| < 1.0   | No        |

## Security Features

### Fail-Closed Design
Unauthorized requests return 402. No access granted without valid payment proof.

### Payment Replay Prevention
Each payment verification includes:
- Transaction timestamp validation
- Nonce tracking
- Maximum age threshold (7 days)

### Minimum Payment Threshold
All payments must meet $0.10 USD minimum to prevent dust attacks.

### No Credential Storage
Payment verification uses read-only RPC calls. No private keys stored.

### Rate Limiting
Built-in request rate limiting per IP and per endpoint.

## Best Practices

### For Users

- Keep dependencies updated
- Use environment variables for secrets
- Enable rate limiting in production
- Monitor payment activity

### For Developers

- Never commit `.env` files
- Validate all inputs
- Use type hints and Pydantic models
- Run tests before commits

## Known Considerations

### PayAI Facilitator
- Third-party dependency
- User addresses visible to PayAI
- Automatic fallback to direct verification on outage

### RPC Endpoints
- Provider rate limits apply
- Use dedicated RPC providers with SLAs
- Implement caching where appropriate

## Contact

security@kamiyo.ai
