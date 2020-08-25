from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, utcnow


class JournalEntry(PublicIdMixin, db.Model):
    """A balanced double-entry journal entry in a single currency."""

    __tablename__ = "journal_entries"
    __public_id_prefix__ = "je"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    currency = db.Column(db.String(3), nullable=False)
    reference_type = db.Column(db.String(30), nullable=False)
    reference_id = db.Column(db.String(40), nullable=False, index=True)
    memo = db.Column(db.String(255), nullable=True)
    posted_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    lines = db.relationship(
        "JournalLine",
        back_populates="entry",
        order_by="JournalLine.id",
        cascade="all, delete-orphan",
    )


class JournalLine(db.Model):
    __tablename__ = "journal_lines"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(
        db.Integer, db.ForeignKey("journal_entries.id"), nullable=False, index=True
    )
    account = db.Column(db.String(40), nullable=False, index=True)
    debit = db.Column(db.Integer, nullable=False, default=0)
    credit = db.Column(db.Integer, nullable=False, default=0)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)

    entry = db.relationship("JournalEntry", back_populates="lines")
