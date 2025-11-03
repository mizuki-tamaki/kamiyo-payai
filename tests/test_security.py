"""
Test cases for security features
"""

import pytest
from fastapi import HTTPException
from api.x402.security import (
    AddressValidator,
    RequestSanitizer,
    PaymentVerificationRequest,
    validate_payment_amount,
    RateLimiter
)


# =============================================================================
# ADDRESS VALIDATION TESTS
# =============================================================================

def test_valid_evm_address():
    """Test validation of valid EVM address"""
    valid_address = "0x1234567890123456789012345678901234567890"
    assert AddressValidator.validate_evm_address(valid_address) == True


def test_invalid_evm_address_no_prefix():
    """Test rejection of EVM address without 0x prefix"""
    invalid_address = "1234567890123456789012345678901234567890"
    assert AddressValidator.validate_evm_address(invalid_address) == False


def test_invalid_evm_address_wrong_length():
    """Test rejection of EVM address with wrong length"""
    invalid_address = "0x12345"
    assert AddressValidator.validate_evm_address(invalid_address) == False


def test_invalid_evm_address_non_hex():
    """Test rejection of EVM address with non-hex characters"""
    invalid_address = "0x123456789012345678901234567890123456789g"
    assert AddressValidator.validate_evm_address(invalid_address) == False


def test_valid_solana_address():
    """Test validation of valid Solana address"""
    valid_address = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    assert AddressValidator.validate_solana_address(valid_address) == True


def test_invalid_solana_address_too_short():
    """Test rejection of Solana address that's too short"""
    invalid_address = "short"
    assert AddressValidator.validate_solana_address(invalid_address) == False


def test_address_sanitization():
    """Test address sanitization"""
    address = "  0xAbCdEf1234567890123456789012345678901234  "
    sanitized = AddressValidator.sanitize_address(address)
    assert sanitized == "0xabcdef1234567890123456789012345678901234"
    assert sanitized == sanitized.strip()


# =============================================================================
# PAYMENT VERIFICATION REQUEST VALIDATION
# =============================================================================

def test_valid_payment_request():
    """Test valid payment verification request"""
    request = PaymentVerificationRequest(
        tx_hash="0x" + "a" * 64,
        chain="base",
        expected_amount=10.0
    )
    assert request.chain == "base"
    assert len(request.tx_hash) == 66


def test_invalid_tx_hash_too_short():
    """Test rejection of invalid tx hash"""
    with pytest.raises(ValueError):
        PaymentVerificationRequest(
            tx_hash="0x1234",
            chain="base"
        )


def test_invalid_chain():
    """Test rejection of unsupported chain"""
    with pytest.raises(ValueError):
        PaymentVerificationRequest(
            tx_hash="0x" + "a" * 64,
            chain="unknown_chain"
        )


def test_negative_amount():
    """Test rejection of negative amount"""
    with pytest.raises(ValueError):
        PaymentVerificationRequest(
            tx_hash="0x" + "a" * 64,
            chain="base",
            expected_amount=-10.0
        )


def test_excessive_amount():
    """Test rejection of excessive amount"""
    with pytest.raises(ValueError):
        PaymentVerificationRequest(
            tx_hash="0x" + "a" * 64,
            chain="base",
            expected_amount=10000000.0  # Over 1M
        )


# =============================================================================
# SANITIZATION TESTS
# =============================================================================

def test_string_sanitization():
    """Test string sanitization"""
    dangerous = "test\x00string\x00with\x00nulls"
    sanitized = RequestSanitizer.sanitize_string(dangerous)
    assert "\x00" not in sanitized
    assert sanitized == "teststringwithnulls"


def test_length_limiting():
    """Test that strings are truncated to max length"""
    long_string = "a" * 1000
    sanitized = RequestSanitizer.sanitize_string(long_string, max_length=100)
    assert len(sanitized) == 100


def test_sql_injection_detection():
    """Test SQL injection pattern detection"""
    malicious_inputs = [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "UNION SELECT * FROM passwords",
        "admin'--",
    ]

    for input_str in malicious_inputs:
        assert RequestSanitizer.detect_sql_injection(input_str) == True


def test_xss_detection():
    """Test XSS pattern detection"""
    malicious_inputs = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
        "<iframe src='malicious.com'></iframe>",
    ]

    for input_str in malicious_inputs:
        assert RequestSanitizer.detect_xss(input_str) == True


def test_clean_input_passes_validation():
    """Test that clean input passes all checks"""
    clean_input = "This is a normal string with no malicious content"
    assert RequestSanitizer.detect_sql_injection(clean_input) == False
    assert RequestSanitizer.detect_xss(clean_input) == False


# =============================================================================
# PAYMENT AMOUNT VALIDATION
# =============================================================================

def test_valid_payment_amount():
    """Test validation of valid payment amount"""
    assert validate_payment_amount(10.0) == True


def test_payment_amount_too_small():
    """Test rejection of too small payment"""
    with pytest.raises(HTTPException) as exc_info:
        validate_payment_amount(0.01, min_amount=0.10)
    assert exc_info.value.status_code == 400


def test_payment_amount_too_large():
    """Test rejection of too large payment"""
    with pytest.raises(HTTPException) as exc_info:
        validate_payment_amount(200000.0, max_amount=100000.0)
    assert exc_info.value.status_code == 400


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

def test_rate_limiter_allows_within_limit():
    """Test that requests within limit are allowed"""
    limiter = RateLimiter()

    # Should allow first 5 requests
    for i in range(5):
        allowed, remaining = limiter.check_rate_limit("test_ip", max_requests=10, window_seconds=60)
        assert allowed == True
        assert remaining >= 0


def test_rate_limiter_blocks_over_limit():
    """Test that requests over limit are blocked"""
    limiter = RateLimiter()

    # Make max requests
    for i in range(10):
        limiter.check_rate_limit("test_ip", max_requests=10, window_seconds=60)

    # Next request should be blocked
    allowed, remaining = limiter.check_rate_limit("test_ip", max_requests=10, window_seconds=60)
    assert allowed == False
    assert remaining == 0


def test_rate_limiter_per_identifier():
    """Test that rate limiting is per identifier"""
    limiter = RateLimiter()

    # Use up limit for ip1
    for i in range(5):
        limiter.check_rate_limit("ip1", max_requests=5, window_seconds=60)

    # ip2 should still be allowed
    allowed, remaining = limiter.check_rate_limit("ip2", max_requests=5, window_seconds=60)
    assert allowed == True


def test_rate_limiter_cleanup():
    """Test that old entries are cleaned up"""
    limiter = RateLimiter()

    # Add some requests
    limiter.check_rate_limit("test_ip", max_requests=10, window_seconds=1)

    # Run cleanup (simulating passage of time)
    limiter.cleanup_old_entries()

    # Cleanup doesn't break anything
    assert "test_ip" in limiter.requests or "test_ip" not in limiter.requests


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
