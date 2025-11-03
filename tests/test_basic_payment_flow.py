"""
End-to-end tests for basic payment flow
Tests the complete payment verification cycle
"""

import pytest
import os
from decimal import Decimal
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set testing environment
os.environ["TESTING"] = "true"
os.environ["X402_BYPASS_VERIFICATION"] = "true"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/kamiyo_test"

from api.main import app
from api.database import Base, get_db
from api.x402.models import X402Payment


# Test database setup
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/kamiyo_test"

engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def test_db():
    """Create test database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(test_db):
    """Get test database session"""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client(db_session):
    """Get test HTTP client with database override"""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test root endpoint returns API info"""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "x402 Payment Gateway"
    assert "supported_chains" in data
    assert "payment_methods" in data


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_supported_chains(client):
    """Test getting supported chains"""
    response = await client.get("/x402/supported-chains")
    assert response.status_code == 200
    data = response.json()
    assert "supported_chains" in data
    assert "base" in data["supported_chains"]
    assert "payment_addresses" in data


@pytest.mark.asyncio
async def test_pricing_info(client):
    """Test getting pricing information"""
    response = await client.get("/x402/pricing")
    assert response.status_code == 200
    data = response.json()
    assert "pricing_tiers" in data
    assert "endpoint_specific_pricing" in data
    assert "payment_methods" in data


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires actual blockchain transaction")
async def test_payment_verification_flow(client):
    """
    Test complete payment verification flow
    This requires an actual blockchain transaction, so it's skipped by default
    """
    # Step 1: Try to access protected endpoint without payment
    response = await client.get("/exploits")

    # Should return 402 if middleware is enabled
    # or 200 with data if middleware is disabled
    assert response.status_code in [200, 402]

    if response.status_code == 402:
        payment_data = response.json()
        assert "price" in payment_data
        assert "merchant" in payment_data
        assert "paymentOptions" in payment_data

    # Step 2: Verify a payment (mock transaction)
    verify_request = {
        "tx_hash": "0x123456789abcdef",
        "chain": "base",
        "expected_amount": 0.01
    }

    # This would fail without actual blockchain verification
    # response = await client.post("/x402/verify-payment", json=verify_request)


@pytest.mark.asyncio
async def test_payment_record_creation(db_session):
    """Test creating payment record in database"""
    from api.x402.database_async import X402DatabaseAsync

    db = X402DatabaseAsync(db_session)

    # Create test payment
    payment = await db.create_payment(
        tx_hash="0xtest123",
        chain="base",
        amount_usdc=Decimal("10.00"),
        from_address="0xpayer123",
        to_address="0xmerchant456",
        block_number=12345,
        confirmations=1,
        risk_score=0.1,
        requests_allocated=1000,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )

    assert payment.id is not None
    assert payment.tx_hash == "0xtest123"
    assert payment.chain == "base"
    assert payment.status == "verified"
    assert payment.requests_remaining == 1000


@pytest.mark.asyncio
async def test_payment_usage_tracking(db_session):
    """Test payment usage tracking"""
    from api.x402.database_async import X402DatabaseAsync

    db = X402DatabaseAsync(db_session)

    # Create payment
    payment = await db.create_payment(
        tx_hash="0xtest456",
        chain="base",
        amount_usdc=Decimal("5.00"),
        from_address="0xpayer789",
        to_address="0xmerchant123",
        block_number=12346,
        confirmations=1,
        risk_score=0.1,
        requests_allocated=500,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )

    # Record usage
    usage = await db.record_usage(
        payment_id=payment.id,
        endpoint="/exploits",
        method="GET",
        status_code=200,
        response_time_ms=150,
        ip_address="127.0.0.1",
        user_agent="test-client"
    )

    assert usage.id is not None
    assert usage.payment_id == payment.id
    assert usage.endpoint == "/exploits"
    assert usage.status_code == 200


@pytest.mark.asyncio
async def test_payment_token_generation(db_session):
    """Test payment token generation and retrieval"""
    from api.x402.database_async import X402DatabaseAsync
    import hashlib

    db = X402DatabaseAsync(db_session)

    # Create payment
    payment = await db.create_payment(
        tx_hash="0xtest789",
        chain="base",
        amount_usdc=Decimal("1.00"),
        from_address="0xpayer321",
        to_address="0xmerchant654",
        block_number=12347,
        confirmations=1,
        risk_score=0.1,
        requests_allocated=100,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )

    # Create token
    token_hash = hashlib.sha256(b"test_token_123").hexdigest()
    token = await db.create_token(
        token_hash=token_hash,
        payment_id=payment.id,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )

    assert token.id is not None
    assert token.payment_id == payment.id

    # Retrieve payment by token
    retrieved_payment = await db.get_payment_by_token_hash(token_hash)
    assert retrieved_payment is not None
    assert retrieved_payment.id == payment.id


@pytest.mark.asyncio
async def test_payment_expiration_cleanup(db_session):
    """Test cleanup of expired payments"""
    from api.x402.database_async import X402DatabaseAsync

    db = X402DatabaseAsync(db_session)

    # Create expired payment
    expired_payment = await db.create_payment(
        tx_hash="0xexpired123",
        chain="base",
        amount_usdc=Decimal("1.00"),
        from_address="0xpayer999",
        to_address="0xmerchant999",
        block_number=12348,
        confirmations=1,
        risk_score=0.1,
        requests_allocated=100,
        expires_at=datetime.utcnow() - timedelta(days=1)  # Already expired
    )

    # Run cleanup
    expired_count = await db.cleanup_expired_payments()

    # Verify payment was marked as expired
    updated_payment = await db.get_payment_by_id(expired_payment.id)
    assert updated_payment.status == "expired"


@pytest.mark.asyncio
async def test_payment_stats(db_session):
    """Test payment statistics aggregation"""
    from api.x402.database_async import X402DatabaseAsync

    db = X402DatabaseAsync(db_session)

    # Create multiple payments
    for i in range(3):
        await db.create_payment(
            tx_hash=f"0xstats{i}",
            chain="base",
            amount_usdc=Decimal("10.00"),
            from_address=f"0xpayer{i}",
            to_address="0xmerchant000",
            block_number=12350 + i,
            confirmations=1,
            risk_score=0.1,
            requests_allocated=1000,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

    # Get stats
    stats = await db.get_payment_stats(hours=24)

    assert stats["total_payments"] == 3
    assert stats["total_amount_usdc"] == 30.0
    assert stats["unique_payers"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
