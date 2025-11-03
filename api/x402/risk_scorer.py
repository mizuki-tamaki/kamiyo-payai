"""
Risk Scoring Engine for x402 Payments
Advanced risk assessment for blockchain payments
"""

import logging
import httpx
from typing import Dict, Optional, List
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class RiskScore:
    """Risk score result with breakdown"""
    score: float  # 0.0 (low risk) to 1.0 (high risk)
    factors: Dict[str, float]
    reason: str
    is_high_risk: bool


class RiskScorer:
    """
    Advanced risk scoring for payment verification

    Factors considered:
    - Transaction age
    - Payment amount patterns
    - Address reputation
    - Chain-specific risks
    - Historical behavior
    """

    def __init__(
        self,
        max_score: float = 1.0,
        reject_threshold: float = 0.8,
        external_api_url: Optional[str] = None,
        external_api_key: Optional[str] = None
    ):
        self.max_score = max_score
        self.reject_threshold = reject_threshold
        self.external_api_url = external_api_url
        self.external_api_key = external_api_key
        self.http_client = httpx.AsyncClient(timeout=5.0)

    async def score_payment(
        self,
        tx_hash: str,
        chain: str,
        amount_usdc: Decimal,
        from_address: str,
        to_address: str,
        block_number: int,
        confirmations: int,
        tx_timestamp: Optional[datetime] = None
    ) -> RiskScore:
        """
        Calculate comprehensive risk score for a payment

        Returns RiskScore with 0.0-1.0 score (0=safe, 1=risky)
        """
        factors = {}

        # 1. Transaction age risk (older = safer)
        factors["age"] = self._score_transaction_age(tx_timestamp)

        # 2. Confirmation risk (more confirmations = safer)
        factors["confirmations"] = self._score_confirmations(confirmations, chain)

        # 3. Amount risk (unusual amounts = riskier)
        factors["amount"] = self._score_amount(amount_usdc)

        # 4. Chain risk (some chains riskier than others)
        factors["chain"] = self._score_chain(chain)

        # 5. Address reputation (if available)
        address_score = await self._score_address_reputation(from_address, chain)
        if address_score is not None:
            factors["address_reputation"] = address_score

        # 6. External risk API (if configured)
        external_score = await self._get_external_risk_score(tx_hash, chain, from_address)
        if external_score is not None:
            factors["external_api"] = external_score

        # Calculate weighted average
        total_score = self._calculate_weighted_score(factors)

        # Determine if high risk
        is_high_risk = total_score >= self.reject_threshold

        # Generate reason
        reason = self._generate_reason(factors, total_score, is_high_risk)

        return RiskScore(
            score=total_score,
            factors=factors,
            reason=reason,
            is_high_risk=is_high_risk
        )

    def _score_transaction_age(self, tx_timestamp: Optional[datetime]) -> float:
        """
        Score based on transaction age
        Newer transactions = slightly higher risk (could be unconfirmed/reorg)
        """
        if not tx_timestamp:
            return 0.3  # Unknown age = moderate risk

        age = datetime.utcnow() - tx_timestamp
        age_minutes = age.total_seconds() / 60

        if age_minutes < 5:
            return 0.4  # Very recent
        elif age_minutes < 30:
            return 0.2  # Recent
        elif age_minutes < 60 * 24:
            return 0.1  # Within 24h
        else:
            return 0.05  # Old transaction (safe)

    def _score_confirmations(self, confirmations: int, chain: str) -> float:
        """
        Score based on confirmations
        More confirmations = lower risk
        """
        # Different chains need different confirmation counts
        required_confirmations = {
            "base": 1,
            "polygon": 3,
            "ethereum": 3,
            "avalanche": 1,
            "solana": 1,
            "sei": 1,
            "iotex": 3,
            "peaq": 1,
        }

        required = required_confirmations.get(chain, 3)

        if confirmations >= required * 2:
            return 0.0  # Well confirmed
        elif confirmations >= required:
            return 0.1  # Adequately confirmed
        elif confirmations >= 1:
            return 0.3  # Some confirmations
        else:
            return 0.7  # Unconfirmed (high risk)

    def _score_amount(self, amount: Decimal) -> float:
        """
        Score based on payment amount
        Very small or very large amounts = slightly higher risk
        """
        amount_float = float(amount)

        if amount_float < 0.10:
            return 0.5  # Suspiciously small (dust attack?)
        elif amount_float < 1.0:
            return 0.1  # Small amount
        elif amount_float < 100.0:
            return 0.05  # Normal amount
        elif amount_float < 1000.0:
            return 0.1  # Large amount
        else:
            return 0.3  # Very large amount (needs verification)

    def _score_chain(self, chain: str) -> float:
        """
        Score based on blockchain network
        Different chains have different risk profiles
        """
        chain_risk = {
            "base": 0.05,      # L2, fast, low risk
            "polygon": 0.1,    # Established, moderate risk
            "ethereum": 0.05,  # Most secure, low risk
            "avalanche": 0.1,  # Fast, moderate risk
            "solana": 0.15,    # Fast but can have issues
            "sei": 0.15,       # Newer chain
            "iotex": 0.2,      # Less established
            "peaq": 0.2,       # Newer chain
        }

        return chain_risk.get(chain, 0.25)  # Unknown chain = higher risk

    async def _score_address_reputation(
        self,
        address: str,
        chain: str
    ) -> Optional[float]:
        """
        Score based on address reputation
        Check if address is known to be malicious or trusted

        In production, this would query:
        - Chainalysis
        - TRM Labs
        - Internal blacklist/whitelist
        """
        # Placeholder for external reputation service
        # In production, integrate with reputation APIs

        # Simple heuristic: check address pattern
        if chain == "solana":
            # Solana addresses are base58
            if len(address) < 32:
                return 0.5  # Invalid address format
        else:
            # EVM addresses start with 0x
            if not address.startswith("0x") or len(address) != 42:
                return 0.6  # Invalid format

        # Check against known bad actors (placeholder)
        known_bad_addresses = set([
            # Add known malicious addresses here
        ])

        if address.lower() in known_bad_addresses:
            return 1.0  # Known bad actor

        # Check against whitelist (placeholder)
        known_good_addresses = set([
            # Add trusted addresses here
        ])

        if address.lower() in known_good_addresses:
            return 0.0  # Known trusted

        return 0.1  # Unknown address (slight risk)

    async def _get_external_risk_score(
        self,
        tx_hash: str,
        chain: str,
        address: str
    ) -> Optional[float]:
        """
        Query external risk scoring API
        Examples: Chainalysis, Elliptic, TRM Labs
        """
        if not self.external_api_url or not self.external_api_key:
            return None

        try:
            response = await self.http_client.post(
                self.external_api_url,
                json={
                    "tx_hash": tx_hash,
                    "chain": chain,
                    "address": address
                },
                headers={"Authorization": f"Bearer {self.external_api_key}"}
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("risk_score", 0.0)
            else:
                logger.warning(f"External risk API returned {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error querying external risk API: {e}")
            return None

    def _calculate_weighted_score(self, factors: Dict[str, float]) -> float:
        """
        Calculate weighted average of all risk factors
        """
        # Weights for each factor
        weights = {
            "age": 0.1,
            "confirmations": 0.3,  # Most important
            "amount": 0.15,
            "chain": 0.15,
            "address_reputation": 0.2,
            "external_api": 0.1
        }

        total_weight = 0.0
        total_score = 0.0

        for factor, score in factors.items():
            weight = weights.get(factor, 0.1)
            total_score += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.5  # Unknown

        final_score = total_score / total_weight
        return min(max(final_score, 0.0), self.max_score)

    def _generate_reason(
        self,
        factors: Dict[str, float],
        total_score: float,
        is_high_risk: bool
    ) -> str:
        """Generate human-readable reason for risk score"""

        if is_high_risk:
            # Find highest risk factor
            highest_factor = max(factors.items(), key=lambda x: x[1])
            factor_name, factor_score = highest_factor

            reasons = {
                "age": "Transaction is very recent",
                "confirmations": "Insufficient confirmations",
                "amount": "Unusual payment amount",
                "chain": "High-risk blockchain network",
                "address_reputation": "Sender address has poor reputation",
                "external_api": "External risk service flagged as risky"
            }

            return f"High risk: {reasons.get(factor_name, 'Multiple risk factors')} (score: {total_score:.2f})"
        else:
            return f"Low risk: All checks passed (score: {total_score:.2f})"

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()


# Global risk scorer instance
_risk_scorer: Optional[RiskScorer] = None


def get_risk_scorer(
    max_score: float = 1.0,
    reject_threshold: float = 0.8,
    external_api_url: Optional[str] = None,
    external_api_key: Optional[str] = None
) -> RiskScorer:
    """Get or create global risk scorer instance"""
    global _risk_scorer

    if _risk_scorer is None:
        _risk_scorer = RiskScorer(
            max_score=max_score,
            reject_threshold=reject_threshold,
            external_api_url=external_api_url,
            external_api_key=external_api_key
        )

    return _risk_scorer
