"""
Security hardening for x402 Payment Gateway
Input validation, rate limiting, and security best practices
"""

import re
import logging
import secrets
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, validator, Field
from fastapi import HTTPException, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# =============================================================================
# INPUT VALIDATION MODELS
# =============================================================================

class PaymentVerificationRequest(BaseModel):
    """Validated payment verification request"""
    tx_hash: str = Field(..., min_length=64, max_length=66)
    chain: str = Field(..., min_length=3, max_length=20)
    expected_amount: Optional[float] = Field(None, ge=0.0, le=1000000.0)

    @validator('tx_hash')
    def validate_tx_hash(cls, v):
        """Validate transaction hash format"""
        # EVM: 0x + 64 hex chars
        # Solana: 87-88 base58 chars
        if v.startswith('0x'):
            if not re.match(r'^0x[a-fA-F0-9]{64}$', v):
                raise ValueError('Invalid EVM transaction hash format')
        else:
            if not re.match(r'^[1-9A-HJ-NP-Za-km-z]{87,88}$', v):
                raise ValueError('Invalid Solana transaction hash format')
        return v.lower()

    @validator('chain')
    def validate_chain(cls, v):
        """Validate chain name"""
        allowed_chains = [
            'base', 'ethereum', 'polygon', 'avalanche',
            'solana', 'sei', 'iotex', 'peaq'
        ]
        if v.lower() not in allowed_chains:
            raise ValueError(f'Unsupported chain: {v}. Allowed: {allowed_chains}')
        return v.lower()


class AddressValidator:
    """Blockchain address validation"""

    @staticmethod
    def validate_evm_address(address: str) -> bool:
        """Validate Ethereum/EVM address"""
        if not address.startswith('0x'):
            return False
        if len(address) != 42:
            return False
        if not re.match(r'^0x[a-fA-F0-9]{40}$', address):
            return False
        return True

    @staticmethod
    def validate_solana_address(address: str) -> bool:
        """Validate Solana address"""
        if len(address) < 32 or len(address) > 44:
            return False
        if not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address):
            return False
        return True

    @staticmethod
    def validate_address(address: str, chain: str) -> bool:
        """Validate address for specific chain"""
        if chain == 'solana':
            return AddressValidator.validate_solana_address(address)
        else:
            return AddressValidator.validate_evm_address(address)

    @staticmethod
    def sanitize_address(address: str) -> str:
        """Sanitize and normalize address"""
        # Remove whitespace
        address = address.strip()

        # EVM addresses are case-insensitive (except checksum)
        # For simplicity, we lowercase them
        if address.startswith('0x'):
            return address.lower()

        return address


# =============================================================================
# API KEY MANAGEMENT
# =============================================================================

class APIKeyManager:
    """Secure API key management"""

    @staticmethod
    def generate_api_key() -> str:
        """Generate cryptographically secure API key"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash API key for storage"""
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def verify_api_key(api_key: str, hashed_key: str) -> bool:
        """Verify API key against hash"""
        return APIKeyManager.hash_api_key(api_key) == hashed_key


# =============================================================================
# ADMIN AUTHENTICATION
# =============================================================================

security = HTTPBearer()


async def verify_admin_key(
    request: Request,
    x_admin_key: Optional[str] = Header(None)
) -> bool:
    """Verify admin API key"""
    from api.x402.config import get_x402_config

    config = get_x402_config()

    # Check for default/insecure admin key
    if config.admin_key in [
        'dev_x402_admin_key_change_in_production',
        'admin',
        'password',
        '12345'
    ]:
        logger.critical("SECURITY: Using default admin key in production!")
        if not is_development_environment():
            raise HTTPException(
                status_code=500,
                detail="Server misconfigured - default credentials detected"
            )

    if not x_admin_key or x_admin_key != config.admin_key:
        logger.warning(f"Unauthorized admin access attempt from {request.client.host}")
        raise HTTPException(
            status_code=403,
            detail="Invalid admin key"
        )

    return True


def is_development_environment() -> bool:
    """Check if running in development mode"""
    import os
    return os.getenv('ENVIRONMENT', 'production').lower() in ['development', 'dev', 'local']


# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """Advanced rate limiting with multiple strategies"""

    def __init__(self):
        self.requests: Dict[str, list] = {}
        self.blocked_ips: Dict[str, datetime] = {}

    def check_rate_limit(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check if request is within rate limit

        Returns: (allowed, remaining_requests)
        """
        now = datetime.utcnow()

        # Check if IP is blocked
        if identifier in self.blocked_ips:
            unblock_time = self.blocked_ips[identifier]
            if now < unblock_time:
                return False, 0
            else:
                del self.blocked_ips[identifier]

        # Initialize or get request history
        if identifier not in self.requests:
            self.requests[identifier] = []

        # Remove old requests outside window
        cutoff = now - timedelta(seconds=window_seconds)
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff
        ]

        # Check if over limit
        current_count = len(self.requests[identifier])
        if current_count >= max_requests:
            # Block IP for double the window time
            self.blocked_ips[identifier] = now + timedelta(seconds=window_seconds * 2)
            logger.warning(f"Rate limit exceeded for {identifier}, blocking temporarily")
            return False, 0

        # Add current request
        self.requests[identifier].append(now)
        remaining = max_requests - (current_count + 1)

        return True, remaining

    def cleanup_old_entries(self):
        """Remove old entries to prevent memory leak"""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)

        # Clean up request history
        for identifier in list(self.requests.keys()):
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if req_time > cutoff
            ]
            if not self.requests[identifier]:
                del self.requests[identifier]

        # Clean up expired blocks
        for ip in list(self.blocked_ips.keys()):
            if self.blocked_ips[ip] < now:
                del self.blocked_ips[ip]


# Global rate limiter
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


# =============================================================================
# REQUEST SANITIZATION
# =============================================================================

class RequestSanitizer:
    """Sanitize and validate incoming requests"""

    @staticmethod
    def sanitize_string(value: str, max_length: int = 255) -> str:
        """Sanitize string input"""
        # Remove null bytes
        value = value.replace('\x00', '')

        # Limit length
        value = value[:max_length]

        # Strip whitespace
        value = value.strip()

        return value

    @staticmethod
    def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """Sanitize HTTP headers"""
        sanitized = {}

        for key, value in headers.items():
            # Only allow alphanumeric and common header chars
            if not re.match(r'^[a-zA-Z0-9\-_]+$', key):
                continue

            # Sanitize value
            value = RequestSanitizer.sanitize_string(value, max_length=1000)
            sanitized[key] = value

        return sanitized

    @staticmethod
    def detect_sql_injection(value: str) -> bool:
        """Detect potential SQL injection patterns"""
        sql_patterns = [
            r"(\bUNION\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b)",
            r"--",
            r"#",
            r"/\*.*\*/",
            r";\s*$"
        ]

        for pattern in sql_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return True

        return False

    @staticmethod
    def detect_xss(value: str) -> bool:
        """Detect potential XSS patterns"""
        xss_patterns = [
            r"<script",
            r"javascript:",
            r"onerror\s*=",
            r"onclick\s*=",
            r"<iframe"
        ]

        for pattern in xss_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return True

        return False

    @staticmethod
    def validate_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize entire request"""
        sanitized = {}

        for key, value in request_data.items():
            if isinstance(value, str):
                # Check for injection attacks
                if RequestSanitizer.detect_sql_injection(value):
                    logger.warning(f"Potential SQL injection detected in {key}")
                    raise HTTPException(status_code=400, detail="Invalid input")

                if RequestSanitizer.detect_xss(value):
                    logger.warning(f"Potential XSS detected in {key}")
                    raise HTTPException(status_code=400, detail="Invalid input")

                # Sanitize
                sanitized[key] = RequestSanitizer.sanitize_string(value)
            else:
                sanitized[key] = value

        return sanitized


# =============================================================================
# SECURITY HEADERS
# =============================================================================

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
}


def add_security_headers(response) -> None:
    """Add security headers to response"""
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value


# =============================================================================
# ENVIRONMENT CHECKS
# =============================================================================

def validate_production_config():
    """Validate that production environment is properly configured"""
    import os
    from api.x402.config import get_x402_config

    if not is_development_environment():
        config = get_x402_config()

        # Check for default credentials
        insecure_defaults = []

        if config.admin_key == 'dev_x402_admin_key_change_in_production':
            insecure_defaults.append("admin_key")

        if '0x742d35Cc6634C0532925a3b8D4B5e3A3A3b7b7b7' in [
            config.base_payment_address,
            config.ethereum_payment_address
        ]:
            insecure_defaults.append("payment_addresses")

        if insecure_defaults:
            error_msg = f"SECURITY ERROR: Default credentials detected in production: {', '.join(insecure_defaults)}"
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        logger.info("Production security configuration validated")


# =============================================================================
# PAYMENT AMOUNT VALIDATION
# =============================================================================

def validate_payment_amount(amount: float, min_amount: float = 0.10, max_amount: float = 100000.0) -> bool:
    """Validate payment amount is within acceptable range"""
    if amount < min_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount too small. Minimum: {min_amount} USDC"
        )

    if amount > max_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount too large. Maximum: {max_amount} USDC"
        )

    return True
