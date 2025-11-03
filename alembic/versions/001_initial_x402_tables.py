"""Initial x402 payment tables

Revision ID: 001_initial
Revises:
Create Date: 2024-11-03 20:55:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create x402 payment tables"""

    # Create x402_payments table
    op.create_table(
        'x402_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tx_hash', sa.String(length=255), nullable=False),
        sa.Column('chain', sa.String(length=50), nullable=False),
        sa.Column('amount_usdc', sa.DECIMAL(precision=18, scale=6), nullable=False),
        sa.Column('from_address', sa.String(length=255), nullable=False),
        sa.Column('to_address', sa.String(length=255), nullable=False),
        sa.Column('block_number', sa.BigInteger(), nullable=False),
        sa.Column('confirmations', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('risk_score', sa.DECIMAL(precision=3, scale=2), server_default='0.1'),
        sa.Column('requests_allocated', sa.Integer(), nullable=False),
        sa.Column('requests_used', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes on x402_payments
    op.create_index('ix_x402_payments_tx_hash', 'x402_payments', ['tx_hash'], unique=True)
    op.create_index('ix_x402_payments_chain', 'x402_payments', ['chain'])
    op.create_index('ix_x402_payments_from_address', 'x402_payments', ['from_address'])
    op.create_index('ix_x402_payments_status', 'x402_payments', ['status'])
    op.create_index('ix_x402_payments_created_at', 'x402_payments', ['created_at'])
    op.create_index('ix_x402_payments_expires_at', 'x402_payments', ['expires_at'])

    # Create x402_tokens table
    op.create_table(
        'x402_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['payment_id'], ['x402_payments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes on x402_tokens
    op.create_index('ix_x402_tokens_token_hash', 'x402_tokens', ['token_hash'], unique=True)
    op.create_index('ix_x402_tokens_payment_id', 'x402_tokens', ['payment_id'])
    op.create_index('ix_x402_tokens_expires_at', 'x402_tokens', ['expires_at'])

    # Create x402_usage table
    op.create_table(
        'x402_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('response_time_ms', sa.Integer()),
        sa.Column('ip_address', sa.String(length=45)),
        sa.Column('user_agent', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['payment_id'], ['x402_payments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes on x402_usage
    op.create_index('ix_x402_usage_payment_id', 'x402_usage', ['payment_id'])
    op.create_index('ix_x402_usage_endpoint', 'x402_usage', ['endpoint'])
    op.create_index('ix_x402_usage_created_at', 'x402_usage', ['created_at'])

    # Create x402_analytics table
    op.create_table(
        'x402_analytics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hour_bucket', sa.DateTime(timezone=True), nullable=False),
        sa.Column('chain', sa.String(length=50), nullable=False),
        sa.Column('total_payments', sa.Integer(), server_default='0'),
        sa.Column('total_amount_usdc', sa.DECIMAL(precision=18, scale=6), server_default='0'),
        sa.Column('total_requests', sa.Integer(), server_default='0'),
        sa.Column('unique_payers', sa.Integer(), server_default='0'),
        sa.Column('average_payment_usdc', sa.DECIMAL(precision=18, scale=6), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes on x402_analytics
    op.create_index('ix_x402_analytics_hour_bucket', 'x402_analytics', ['hour_bucket'])
    op.create_index('ix_x402_analytics_chain', 'x402_analytics', ['chain'])


def downgrade() -> None:
    """Drop x402 payment tables"""
    op.drop_index('ix_x402_analytics_chain', table_name='x402_analytics')
    op.drop_index('ix_x402_analytics_hour_bucket', table_name='x402_analytics')
    op.drop_table('x402_analytics')

    op.drop_index('ix_x402_usage_created_at', table_name='x402_usage')
    op.drop_index('ix_x402_usage_endpoint', table_name='x402_usage')
    op.drop_index('ix_x402_usage_payment_id', table_name='x402_usage')
    op.drop_table('x402_usage')

    op.drop_index('ix_x402_tokens_expires_at', table_name='x402_tokens')
    op.drop_index('ix_x402_tokens_payment_id', table_name='x402_tokens')
    op.drop_index('ix_x402_tokens_token_hash', table_name='x402_tokens')
    op.drop_table('x402_tokens')

    op.drop_index('ix_x402_payments_expires_at', table_name='x402_payments')
    op.drop_index('ix_x402_payments_created_at', table_name='x402_payments')
    op.drop_index('ix_x402_payments_status', table_name='x402_payments')
    op.drop_index('ix_x402_payments_from_address', table_name='x402_payments')
    op.drop_index('ix_x402_payments_chain', table_name='x402_payments')
    op.drop_index('ix_x402_payments_tx_hash', table_name='x402_payments')
    op.drop_table('x402_payments')
