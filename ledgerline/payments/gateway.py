"""Payment gateway adapters.

Production deployments plug in a real processor; the ``fake`` gateway is used
in development and tests. It understands a set of magic tokens::

    tok_visa, tok_mastercard   always succeed
    tok_chargeDeclined         card_declined
    tok_insufficientFunds      insufficient_funds
    tok_expiredCard            expired_card
    tok_failOnce               fails the first charge, succeeds afterwards
"""
import collections
import hashlib

from flask import current_app

ChargeResult = collections.namedtuple(
    "ChargeResult", ["succeeded", "reference", "failure_code", "failure_message"]
)

CARD_TOKENS = {
    "tok_visa": ("visa", "4242"),
    "tok_mastercard": ("mastercard", "4444"),
    "tok_chargeDeclined": ("visa", "0002"),
    "tok_insufficientFunds": ("visa", "9995"),
    "tok_expiredCard": ("visa", "0069"),
    "tok_failOnce": ("visa", "0341"),
}

FAILURES = {
    "tok_chargeDeclined": ("card_declined", "Your card was declined."),
    "tok_insufficientFunds": ("insufficient_funds", "Your card has insufficient funds."),
    "tok_expiredCard": ("expired_card", "Your card has expired."),
}


class PaymentGateway:
    def describe_token(self, token):
        """Return ``(brand, last4)`` for a token, or raise ``ValueError``."""
        raise NotImplementedError

    def charge(self, amount, currency, token, idempotency_key, description=None):
        raise NotImplementedError


class FakeGateway(PaymentGateway):
    def __init__(self):
        self.charges = []
        self._by_key = {}
        self._fail_once_seen = set()

    def describe_token(self, token):
        try:
            return CARD_TOKENS[token]
        except KeyError:
            raise ValueError("Unknown card token %r" % (token,))

    def charge(self, amount, currency, token, idempotency_key, description=None):
        if idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        reference = "ch_" + hashlib.sha1(idempotency_key.encode("utf-8")).hexdigest()[:24]
        if token in FAILURES:
            code, message = FAILURES[token]
            result = ChargeResult(False, reference, code, message)
        elif token == "tok_failOnce" and token not in self._fail_once_seen:
            self._fail_once_seen.add(token)
            result = ChargeResult(False, reference, "processing_error", "Try again later.")
        elif token in CARD_TOKENS:
            result = ChargeResult(True, reference, None, None)
        else:
            result = ChargeResult(False, reference, "invalid_token", "Unknown payment token.")
        self._by_key[idempotency_key] = result
        self.charges.append(
            {
                "amount": amount,
                "currency": currency,
                "token": token,
                "idempotency_key": idempotency_key,
                "succeeded": result.succeeded,
                "description": description,
            }
        )
        return result


GATEWAYS = {"fake": FakeGateway}


def init_gateway(app):
    name = app.config["LEDGERLINE_PAYMENT_GATEWAY"]
    try:
        app.extensions["ledgerline.gateway"] = GATEWAYS[name]()
    except KeyError:
        raise RuntimeError("Unknown payment gateway %r" % (name,))


def get_gateway():
    return current_app.extensions["ledgerline.gateway"]
