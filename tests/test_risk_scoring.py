"""
Test cases for risk scoring system
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from api.x402.risk_scorer import RiskScorer, RiskScore


@pytest.fixture
def risk_scorer():
    """Create risk scorer instance"""
    return RiskScorer(max_score=1.0, reject_threshold=0.8)


@pytest.mark.asyncio
async def test_low_risk_payment(risk_scorer):
    """Test scoring of low-risk payment"""
    score = await risk_scorer.score_payment(
        tx_hash="0x1234567890abcdef" * 4,
        chain="base",
        amount_usdc=Decimal("10.00"),
        from_address="0x1234567890123456789012345678901234567890",
        to_address="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        block_number=12345,
        confirmations=5,
        tx_timestamp=datetime.utcnow() - timedelta(hours=1)
    )

    assert isinstance(score, RiskScore)
    assert 0.0 <= score.score <= 1.0
    assert score.is_high_risk == False
    assert "age" in score.factors
    assert "confirmations" in score.factors
    assert "amount" in score.factors


@pytest.mark.asyncio
async def test_high_risk_unconfirmed_payment(risk_scorer):
    """Test scoring of unconfirmed payment"""
    score = await risk_scorer.score_payment(
        tx_hash="0x" + "a" * 64,
        chain="base",
        amount_usdc=Decimal("100.00"),
        from_address="0x" + "1" * 40,
        to_address="0x" + "2" * 40,
        block_number=12345,
        confirmations=0,  # Unconfirmed
        tx_timestamp=datetime.utcnow()  # Very recent
    )

    assert score.score > 0.3  # Should have elevated risk
    assert score.factors["confirmations"] > 0.5  # Confirmations factor should be high


@pytest.mark.asyncio
async def test_suspicious_amount(risk_scorer):
    """Test scoring of suspicious payment amount"""
    # Very small amount (dust attack?)
    score = await risk_scorer.score_payment(
        tx_hash="0x" + "b" * 64,
        chain="polygon",
        amount_usdc=Decimal("0.01"),  # Suspiciously small
        from_address="0x" + "3" * 40,
        to_address="0x" + "4" * 40,
        block_number=12345,
        confirmations=3,
        tx_timestamp=datetime.utcnow() - timedelta(hours=2)
    )

    assert score.factors["amount"] > 0.3  # Amount should be flagged


@pytest.mark.asyncio
async def test_chain_risk_scoring(risk_scorer):
    """Test that different chains have different risk profiles"""
    base_params = {
        "tx_hash": "0x" + "c" * 64,
        "amount_usdc": Decimal("10.00"),
        "from_address": "0x" + "5" * 40,
        "to_address": "0x" + "6" * 40,
        "block_number": 12345,
        "confirmations": 3,
        "tx_timestamp": datetime.utcnow() - timedelta(hours=1)
    }

    # Score on Base (low risk)
    score_base = await risk_scorer.score_payment(chain="base", **base_params)

    # Score on less established chain (higher risk)
    score_peaq = await risk_scorer.score_payment(chain="peaq", **base_params)

    assert score_peaq.factors["chain"] > score_base.factors["chain"]


@pytest.mark.asyncio
async def test_invalid_address_format(risk_scorer):
    """Test detection of invalid address format"""
    score = await risk_scorer.score_payment(
        tx_hash="0x" + "d" * 64,
        chain="base",
        amount_usdc=Decimal("10.00"),
        from_address="invalid_address",  # Invalid format
        to_address="0x" + "7" * 40,
        block_number=12345,
        confirmations=3,
        tx_timestamp=datetime.utcnow()
    )

    # Should have elevated address reputation risk
    if "address_reputation" in score.factors:
        assert score.factors["address_reputation"] > 0.3


@pytest.mark.asyncio
async def test_risk_score_factors(risk_scorer):
    """Test that all expected risk factors are included"""
    score = await risk_scorer.score_payment(
        tx_hash="0x" + "e" * 64,
        chain="base",
        amount_usdc=Decimal("10.00"),
        from_address="0x" + "8" * 40,
        to_address="0x" + "9" * 40,
        block_number=12345,
        confirmations=3,
        tx_timestamp=datetime.utcnow() - timedelta(hours=1)
    )

    required_factors = ["age", "confirmations", "amount", "chain"]
    for factor in required_factors:
        assert factor in score.factors


@pytest.mark.asyncio
async def test_reject_threshold(risk_scorer):
    """Test high risk rejection threshold"""
    # Create conditions for high risk score
    score = await risk_scorer.score_payment(
        tx_hash="0x" + "f" * 64,
        chain="peaq",  # Higher risk chain
        amount_usdc=Decimal("0.05"),  # Suspicious amount
        from_address="0x" + "a" * 40,
        to_address="0x" + "b" * 40,
        block_number=12345,
        confirmations=0,  # Unconfirmed
        tx_timestamp=datetime.utcnow()  # Very recent
    )

    # Check if properly flagged based on threshold
    if score.score >= risk_scorer.reject_threshold:
        assert score.is_high_risk == True
    else:
        assert score.is_high_risk == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
