"""Ozow payment gateway integration for real PayShap / EFT payments.

Ozow (ozow.com) is a South African payment gateway ideal for sole developers
and small businesses. It supports PayShap, EFT, and card payments through a
hosted payment page model.

Flow:
  1. Create a payment request (this module) -> get a hosted payment URL
  2. Redirect the customer to that URL (they pay on Ozow's secure page)
  3. Ozow redirects the customer back to SuccessUrl / CancelUrl / ErrorUrl
  4. Ozow also sends a server-to-server POST to NotifyUrl with the final status

Required env vars:
  OZOW_SITE_CODE  - your Ozow merchant site code
  OZOW_API_KEY    - your Ozow private API key (used for request signing)
  OZOW_IS_TEST    - "true" for sandbox/test mode, "false" for live payments
"""
import os
import hashlib
import logging
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

OZOW_API_URL = os.environ.get("OZOW_API_URL", "https://api.ozow.com")
OZOW_SITE_CODE = os.environ.get("OZOW_SITE_CODE", "")
OZOW_API_KEY = os.environ.get("OZOW_API_KEY", "")
OZOW_IS_TEST = os.environ.get("OZOW_IS_TEST", "false").lower() == "true"


def is_configured():
    """Return True if the minimum Ozow credentials are present."""
    return bool(OZOW_SITE_CODE and OZOW_API_KEY)


def _generate_hash(params):
    """Generate the Ozow security hash for request signing.

    Algorithm: sort params alphabetically, concatenate key+value pairs with no
    separators, prepend and append the API key, SHA256 hash, uppercase hex.
    """
    filtered = {
        k: str(v) for k, v in params.items()
        if v is not None and str(v) != "" and k.lower() != "hash"
    }
    sorted_keys = sorted(filtered.keys())
    concat = "".join(f"{k}{filtered[k]}" for k in sorted_keys)
    input_str = OZOW_API_KEY + concat + OZOW_API_KEY
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest().upper()


def create_payment(*, amount, reference, customer_email=None,
                   success_url, cancel_url, error_url, notify_url):
    """Create an Ozow payment request and return the hosted payment page URL.

    Returns a dict with:
      - url:            redirect URL for the customer's browser
      - transaction_id: Ozow's payment request id (for later status checks)
    """
    if not is_configured():
        raise OzowError(
            "Ozow is not configured. Set OZOW_SITE_CODE and OZOW_API_KEY "
            "in your environment."
        )

    amount_str = f"{Decimal(str(amount)):.2f}"

    params = {
        "SiteCode": OZOW_SITE_CODE,
        "CountryCode": "ZA",
        "CurrencyCode": "ZAR",
        "Amount": amount_str,
        "TransactionReference": reference,
        "BankReference": reference,
        "OptionalCustomerEmail": customer_email or "",
        "CancelUrl": cancel_url,
        "ErrorUrl": error_url,
        "SuccessUrl": success_url,
        "NotifyUrl": notify_url,
        "IsTest": str(OZOW_IS_TEST).lower(),
    }

    params["Hash"] = _generate_hash(params)

    url = f"{OZOW_API_URL}/v1/PaymentRequest"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    resp = requests.post(url, json=params, headers=headers, timeout=30)

    if resp.status_code != 200:
        raise OzowError(
            f"Ozow payment request failed (HTTP {resp.status_code}): "
            f"{resp.text[:300]}"
        )

    data = resp.json()
    payment_url = (
        data.get("url")
        or data.get("Url")
        or data.get("paymentUrl")
    )
    transaction_id = (
        data.get("paymentRequestId")
        or data.get("PaymentRequestId")
        or data.get("id")
    )

    if not payment_url:
        raise OzowError(
            f"Ozow did not return a payment URL. Response: {str(data)[:300]}"
        )

    return {
        "url": payment_url,
        "transaction_id": str(transaction_id) if transaction_id else "",
    }


def verify_notification(data_dict):
    """Verify the hash on an Ozow server-to-server notification.

    Returns True if the hash matches (authentic callback from Ozow).
    """
    received_hash = data_dict.get("Hash") or data_dict.get("hash", "")
    if not received_hash:
        return False
    computed = _generate_hash(data_dict)
    return computed.upper() == received_hash.upper()


STATUS_SUCCESS = {"COMPLETE", "COMPLETED", "SUCCESS", "SUCCESSFUL", "PAID"}
STATUS_FAILED = {"FAILED", "ERROR", "DECLINED", "ABANDONED"}
STATUS_CANCELLED = {"CANCELLED", "CANCELED"}
STATUS_PENDING = {"PENDING", "PROCESSING", "IN_PROGRESS"}


class OzowError(Exception):
    pass
