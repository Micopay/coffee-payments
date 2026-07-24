"""
Tests for XLM-06 multichain schema support and migration.
"""

import json
import os
import sqlite3
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError

from core.models import Base, Producer, User, Payment, EscrowDetail, Wallet, PaymentStatus
from scripts.migrate_004_multichain import migrate


@pytest.fixture
def db_session(tmp_path):
    """Fixture providing a fresh in-memory SQLite database with latest schema."""
    db_file = tmp_path / "test_multichain.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()


def test_xrpl_address_shim_returns_same_address(db_session):
    """Legacy xrpl_address getter/setter returns same address as address_for('XRPL')."""
    xrpl_addr = "rKsq2QsB4erZ9QvixAhg9f8TZPqB2bwJvc"
    producer = Producer(name="Productor Test XRPL", xrpl_address=xrpl_addr)
    db_session.add(producer)
    db_session.commit()

    assert producer.xrpl_address == xrpl_addr
    assert producer.address_for("XRPL") == xrpl_addr

    # Check Wallet record created by trigger/event
    w = db_session.query(Wallet).filter_by(owner_type="producer", owner_id=producer.id, network="XRPL").first()
    assert w is not None
    assert w.address == xrpl_addr


def test_stellar_only_producer_valid(db_session):
    """A producer without an XRPL address but with a Stellar address is valid."""
    stellar_addr = "GCXKG6RN4SUUCFQXG3XW7HN7WVAK2S2A6W2CYU3S7Z6L2F"
    producer = Producer(name="Productor Solo Stellar")
    db_session.add(producer)
    db_session.commit()

    producer.set_address("STELLAR", stellar_addr, is_default=True)
    db_session.commit()

    assert producer.address_for("STELLAR") == stellar_addr
    assert producer.address_for("XRPL") is None
    assert producer.xrpl_address is None


def test_wallet_network_address_uniqueness(db_session):
    """Uniqueness constraint on (network, address) must be enforced."""
    w1 = Wallet(owner_type="producer", owner_id=1, network="XRPL", address="rDuplicateAddr123", is_default=True)
    db_session.add(w1)
    db_session.commit()

    w2 = Wallet(owner_type="producer", owner_id=2, network="XRPL", address="rDuplicateAddr123", is_default=True)
    db_session.add(w2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_escrow_detail_chain_data_json_roundtrip(db_session):
    """chain_data JSON serialization/deserialization works for both XRPL and STELLAR."""
    # 1. XRPL Escrow contract C4
    xrpl_chain_data = {
        "offer_sequence": 42,
        "condition_hex": "A02580201234567890ABCDEF1234567890ABCDEF1234567890ABCDEF12345678810120",
        "fulfillment_hex": "A02280201234567890ABCDEF1234567890ABCDEF1234567890ABCDEF12345678"
    }

    producer = Producer(name="Producer Escrow", xrpl_address="rProducerEscrow123")
    user = User(username="op_escrow", full_name="Operator Escrow")
    db_session.add_all([producer, user])
    db_session.commit()

    payment = Payment(
        uetr=str(uuid.uuid4()),
        tx_hash="HASH12345",
        amount=100,
        currency="XRP",
        producer_id=producer.id,
        operator_id=user.id,
        status=PaymentStatus.ESCROWED
    )
    db_session.add(payment)
    db_session.commit()

    escrow = EscrowDetail(
        payment_id=payment.id,
        network="XRPL",
        chain_data=json.dumps(xrpl_chain_data),
        cancel_after=datetime.now(timezone.utc),
        create_tx_hash="HASH12345"
    )
    db_session.add(escrow)
    db_session.commit()

    assert escrow.offer_sequence == 42
    assert escrow.condition_hex == xrpl_chain_data["condition_hex"]
    assert escrow.fulfillment_hex == xrpl_chain_data["fulfillment_hex"]

    # 2. Stellar Escrow contract C4
    stellar_chain_data = {
        "escrow_account": "GCXKG6RN4SUUCFQXG3XW7HN7WVAK2S2A6W2CYU3S7Z6L2F",
        "release_xdr": "AAAAAgAAAAD...",
        "refund_xdr": "AAAAAQAAAAC...",
        "sequence": "123456"
    }

    payment_st = Payment(
        uetr=str(uuid.uuid4()),
        network="STELLAR",
        tx_hash="HASH_STELLAR_999",
        amount=200,
        currency="XLM",
        producer_id=producer.id,
        operator_id=user.id,
        status=PaymentStatus.ESCROWED
    )
    db_session.add(payment_st)
    db_session.commit()

    escrow_st = EscrowDetail(
        payment_id=payment_st.id,
        network="STELLAR",
        chain_data=json.dumps(stellar_chain_data),
        cancel_after=datetime.now(timezone.utc),
        create_tx_hash="HASH_STELLAR_999"
    )
    db_session.add(escrow_st)
    db_session.commit()

    retrieved_data = json.loads(escrow_st.chain_data)
    assert retrieved_data == stellar_chain_data


def test_migration_idempotent(tmp_path):
    """Migration running on a legacy database is idempotent and non-destructive."""
    db_path = str(tmp_path / "legacy_test.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create legacy tables
    cursor.execute("""
        CREATE TABLE producers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            xrpl_address TEXT NOT NULL UNIQUE
        );
    """)
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            xrpl_address TEXT
        );
    """)
    cursor.execute("""
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY,
            uetr TEXT NOT NULL,
            xrpl_tx_hash TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE escrow_details (
            id INTEGER PRIMARY KEY,
            payment_id INTEGER NOT NULL,
            offer_sequence INTEGER NOT NULL,
            condition_hex TEXT NOT NULL,
            fulfillment_hex TEXT NOT NULL,
            cancel_after TEXT NOT NULL,
            create_tx_hash TEXT NOT NULL
        );
    """)

    # Populate legacy data
    cursor.execute("INSERT INTO producers (id, name, xrpl_address) VALUES (1, 'Legacy Producer', 'rLegacyProducer123');")
    cursor.execute("INSERT INTO users (id, username, xrpl_address) VALUES (1, 'legacy_op', 'rLegacyOperator123');")
    cursor.execute("INSERT INTO payments (id, uetr, xrpl_tx_hash) VALUES (1, 'uetr-1', 'HASH_LEGACY_1');")
    cursor.execute("INSERT INTO escrow_details (id, payment_id, offer_sequence, condition_hex, fulfillment_hex, cancel_after, create_tx_hash) VALUES (1, 1, 99, 'COND99', 'FUL99', '2026-01-01', 'HASH_LEGACY_1');")
    conn.commit()
    conn.close()

    # Run migration first time
    migrate(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Verify wallets created
    cursor.execute("SELECT owner_type, owner_id, network, address FROM wallets;")
    wallets = cursor.fetchall()
    assert len(wallets) == 2
    assert ('producer', 1, 'XRPL', 'rLegacyProducer123') in wallets
    assert ('user', 1, 'XRPL', 'rLegacyOperator123') in wallets

    # Verify payments renamed column and network added
    cursor.execute("PRAGMA table_info(payments);")
    cols = [r[1] for r in cursor.fetchall()]
    assert "tx_hash" in cols
    assert "xrpl_tx_hash" not in cols
    assert "network" in cols

    # Verify escrow_details chain_data
    cursor.execute("SELECT network, chain_data FROM escrow_details WHERE id = 1;")
    esc_row = cursor.fetchone()
    assert esc_row[0] == "XRPL"
    esc_dict = json.loads(esc_row[1])
    assert esc_dict["offer_sequence"] == 99
    assert esc_dict["condition_hex"] == "COND99"
    assert esc_dict["fulfillment_hex"] == "FUL99"
    conn.close()

    # Run migration second time (idempotency check)
    migrate(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM wallets;")
    assert cursor.fetchone()[0] == 2
    conn.close()
