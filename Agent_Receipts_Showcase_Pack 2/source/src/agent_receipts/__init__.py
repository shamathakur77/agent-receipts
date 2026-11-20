"""Agent Receipts: a hash-chained audit trail for AI agent actions."""
from .ledger import (DEFAULT_RETENTION_DAYS, GENESIS, RECEIPT_FIELDS, SCHEMA, Ledger, LedgerError,
                     VerifyResult, verify_ledger)
from .wrap import ReceiptedSession, receipted

__version__ = "0.1.0"
__all__ = ["Ledger", "LedgerError", "ReceiptedSession", "receipted", "verify_ledger", "VerifyResult",
           "RECEIPT_FIELDS", "SCHEMA", "GENESIS", "DEFAULT_RETENTION_DAYS", "__version__"]
