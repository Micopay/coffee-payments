"""
Database models for the Coffee Multichain Payment Platform

Tables:
- User: System operators (admin and payment app users)
- Producer: Coffee producers receiving payments
- Wallet: Multichain wallet addresses for users and producers
- Payment: Multichain payment records (XRPL, Stellar)
- EscrowDetail: Escrow details for quality-conditional payments
- Delivery: Coffee delivery records (weight, price)
- IsoMessage: ISO 20022 XML messages
- AuditLog: System audit trail
- DailyPrice: Reference price for coffee per kg
- AppConfig: Application key-value encrypted configuration
"""

import enum
import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Numeric, Text,
    ForeignKey, Enum as SQLEnum, Boolean, UniqueConstraint, event
)
from sqlalchemy.orm import relationship, declarative_base, object_session

Base = declarative_base()


class UserRole(enum.Enum):
    """User roles in the system"""
    ADMIN = "admin"
    OPERATOR = "operator"


class PaymentStatus(enum.Enum):
    """Payment status enumeration"""
    PENDING   = "pending"
    COMPLETED = "completed"
    FAILED    = "failed"
    SIMULATED = "simulated"   # pagos no-XRP (tokens simulados)
    ESCROWED  = "escrowed"    # fondos bloqueados en escrow, pendiente de calidad
    REJECTED  = "rejected"    # calidad rechazada; reembolso on-ledger pendiente de vencimiento
    REFUNDED  = "refunded"    # EscrowCancel ejecutado; fondos devueltos al operador


class Wallet(Base):
    """Multichain wallet addresses for producers and users"""
    __tablename__ = "wallets"

    id         = Column(Integer, primary_key=True)
    owner_type = Column(String(20), nullable=False)    # 'producer' | 'user'
    owner_id   = Column(Integer,    nullable=False)
    network    = Column(String(20), nullable=False)    # 'XRPL' | 'STELLAR'
    address    = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("network", "address", name="uq_wallet_net_addr"),)


class User(Base):
    """System users (admin and operators)"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)  # Generated ID
    password_hash = Column(String(255), nullable=True)  # Nullable for first login
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.OPERATOR)
    full_name = Column(String(200), nullable=False)
    date_of_birth = Column(DateTime, nullable=True)
    _legacy_xrpl_address = Column("xrpl_address", String(100), nullable=True)  # For backward compatibility
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)

    _owner_type = "user"

    # Relationships
    payments = relationship("Payment", back_populates="operator")
    audit_logs = relationship("AuditLog", back_populates="user")

    def address_for(self, network: str) -> str | None:
        """Get default address for given network ('XRPL' or 'STELLAR')."""
        session = object_session(self)
        if session and self.id:
            w = session.query(Wallet).filter_by(
                owner_type=self._owner_type,
                owner_id=self.id,
                network=network
            ).order_by(Wallet.is_default.desc(), Wallet.id.asc()).first()
            if w:
                return w.address
        if network == "XRPL":
            return self._legacy_xrpl_address
        return None

    def set_address(self, network: str, address: str, is_default: bool = True) -> None:
        """Set address for given network ('XRPL' or 'STELLAR')."""
        if network == "XRPL":
            self._legacy_xrpl_address = address
        session = object_session(self)
        if session and self.id:
            w = session.query(Wallet).filter_by(
                owner_type=self._owner_type,
                owner_id=self.id,
                network=network
            ).first()
            if w:
                w.address = address
                w.is_default = is_default
            else:
                w = Wallet(
                    owner_type=self._owner_type,
                    owner_id=self.id,
                    network=network,
                    address=address,
                    is_default=is_default
                )
                session.add(w)

    @property
    def xrpl_address(self) -> str | None:
        return self.address_for("XRPL")

    @xrpl_address.setter
    def xrpl_address(self, value: str | None) -> None:
        self._legacy_xrpl_address = value
        if value:
            self.set_address("XRPL", value)


class Producer(Base):
    """Coffee producers"""
    __tablename__ = "producers"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    _legacy_xrpl_address = Column("xrpl_address", String(100), nullable=True)  # Backward compatibility
    id_image_path = Column(String(500), nullable=True)  # Path to ID image
    contact_info = Column(Text, nullable=True)
    rfc_encrypted = Column(String(500), nullable=True)  # Encrypted RFC
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    _owner_type = "producer"

    # Relationships
    payments = relationship("Payment", back_populates="producer")

    def address_for(self, network: str) -> str | None:
        """Get default address for given network ('XRPL' or 'STELLAR')."""
        session = object_session(self)
        if session and self.id:
            w = session.query(Wallet).filter_by(
                owner_type=self._owner_type,
                owner_id=self.id,
                network=network
            ).order_by(Wallet.is_default.desc(), Wallet.id.asc()).first()
            if w:
                return w.address
        if network == "XRPL":
            return self._legacy_xrpl_address
        return None

    def set_address(self, network: str, address: str, is_default: bool = True) -> None:
        """Set address for given network ('XRPL' or 'STELLAR')."""
        if network == "XRPL":
            self._legacy_xrpl_address = address
        session = object_session(self)
        if session and self.id:
            w = session.query(Wallet).filter_by(
                owner_type=self._owner_type,
                owner_id=self.id,
                network=network
            ).first()
            if w:
                w.address = address
                w.is_default = is_default
            else:
                w = Wallet(
                    owner_type=self._owner_type,
                    owner_id=self.id,
                    network=network,
                    address=address,
                    is_default=is_default
                )
                session.add(w)

    @property
    def xrpl_address(self) -> str | None:
        return self.address_for("XRPL")

    @xrpl_address.setter
    def xrpl_address(self, value: str | None) -> None:
        self._legacy_xrpl_address = value
        if value:
            self.set_address("XRPL", value)


def _sync_wallet_after_insert(mapper, connection, target):
    """Ensure newly persisted Producer or User gets a Wallet record if xrpl_address was provided."""
    if target._legacy_xrpl_address and target.id:
        from sqlalchemy import text
        res = connection.execute(
            text("SELECT id FROM wallets WHERE owner_type = :ot AND owner_id = :oid AND network = 'XRPL'"),
            {"ot": target._owner_type, "oid": target.id}
        ).fetchone()
        if not res:
            connection.execute(
                text("""
                    INSERT INTO wallets (owner_type, owner_id, network, address, is_default, created_at)
                    VALUES (:ot, :oid, 'XRPL', :addr, 1, :now)
                """),
                {
                    "ot": target._owner_type,
                    "oid": target.id,
                    "addr": target._legacy_xrpl_address,
                    "now": datetime.now(timezone.utc)
                }
            )

event.listen(User, "after_insert", _sync_wallet_after_insert)
event.listen(Producer, "after_insert", _sync_wallet_after_insert)


class Payment(Base):
    """Multichain payment records"""
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True)
    uetr = Column(String(36), unique=True, nullable=False)  # UUID v4
    network = Column(String(20), nullable=False, default="XRPL")
    tx_hash = Column(String(100), unique=True, nullable=False)
    amount = Column(Numeric(18, 8), nullable=False)
    currency = Column(String(10), nullable=False)  # XRP, USDC, RLUSD, MXN, XLM
    amount_mxn = Column(Numeric(15, 2), nullable=True)  # Original amount in MXN
    producer_id = Column(Integer, ForeignKey("producers.id"), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    notes = Column(Text, nullable=True)
    
    # Relationships
    producer = relationship("Producer", back_populates="payments")
    operator = relationship("User", back_populates="payments")
    delivery = relationship("Delivery", back_populates="payment", uselist=False)
    iso_messages = relationship("IsoMessage", back_populates="payment")

    @property
    def xrpl_tx_hash(self) -> str:
        return self.tx_hash

    @xrpl_tx_hash.setter
    def xrpl_tx_hash(self, value: str) -> None:
        self.tx_hash = value


class EscrowDetail(Base):
    """Multichain escrow details for quality-conditional payments"""
    __tablename__ = "escrow_details"

    id              = Column(Integer, primary_key=True)
    payment_id      = Column(Integer, ForeignKey("payments.id"), nullable=False, unique=True)
    network         = Column(String(20), nullable=False, default="XRPL")
    chain_data      = Column(Text, nullable=False)
    cancel_after    = Column(DateTime, nullable=False)
    create_tx_hash  = Column(String(100), nullable=False)
    finish_tx_hash  = Column(String(100), nullable=True)
    cancel_tx_hash  = Column(String(100), nullable=True)
    quality_notes   = Column(Text, nullable=True)
    resolved_at     = Column(DateTime, nullable=True)

    payment = relationship("Payment", backref="escrow_detail")

    def _get_chain_dict(self) -> dict:
        if self.chain_data:
            try:
                return json.loads(self.chain_data)
            except Exception:
                pass
        return {}

    def _set_chain_dict(self, d: dict) -> None:
        self.chain_data = json.dumps(d)

    @property
    def offer_sequence(self) -> int | None:
        return self._get_chain_dict().get("offer_sequence")

    @offer_sequence.setter
    def offer_sequence(self, val: int) -> None:
        d = self._get_chain_dict()
        d["offer_sequence"] = val
        self._set_chain_dict(d)

    @property
    def condition_hex(self) -> str | None:
        return self._get_chain_dict().get("condition_hex")

    @condition_hex.setter
    def condition_hex(self, val: str) -> None:
        d = self._get_chain_dict()
        d["condition_hex"] = val
        self._set_chain_dict(d)

    @property
    def fulfillment_hex(self) -> str | None:
        return self._get_chain_dict().get("fulfillment_hex")

    @fulfillment_hex.setter
    def fulfillment_hex(self, val: str) -> None:
        d = self._get_chain_dict()
        d["fulfillment_hex"] = val
        self._set_chain_dict(d)


class Delivery(Base):
    """Coffee delivery records"""
    __tablename__ = "deliveries"
    
    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, unique=True)
    weight_kg = Column(Numeric(10, 3), nullable=False)
    price_per_kg = Column(Numeric(10, 2), nullable=False)
    total_mxn = Column(Numeric(15, 2), nullable=False)
    delivery_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text, nullable=True)
    
    # Relationships
    payment = relationship("Payment", back_populates="delivery")


class MessageType(enum.Enum):
    """ISO 20022 message types"""
    PACS_008 = "pacs.008"
    PACS_002 = "pacs.002"
    CAMT_053 = "camt.053"
    CAMT_054 = "camt.054"


class IsoMessage(Base):
    """ISO 20022 XML messages"""
    __tablename__ = "iso_messages"
    
    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)
    message_type = Column(SQLEnum(MessageType), nullable=False)
    xml_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    payment = relationship("Payment", back_populates="iso_messages")


class AuditLog(Base):
    """System audit trail"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="audit_logs")


class DailyPrice(Base):
    """Daily reference price for coffee kg set by admin"""
    __tablename__ = "daily_prices"

    id = Column(Integer, primary_key=True)
    price_date = Column(DateTime, nullable=False, unique=True)
    price_per_kg = Column(Numeric(10, 2), nullable=False)
    set_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    set_by_user = relationship("User", foreign_keys=[set_by_user_id])


class AppConfig(Base):
    """Key/value store for local app configuration (values stored encrypted)."""
    __tablename__ = "app_config"

    id    = Column(Integer, primary_key=True)
    key   = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)   # Fernet-encrypted
