"""Stitch payment gateway integration for real PayShap payments.

Stitch (stitch.money) is a South African payment gateway that supports
PayShap bank-to-bank transfers. This module handles:
  1. OAuth2 client-credentials token exchange
  2. Creating a payment intent via Stitch's GraphQL API
  3. Returning the redirect URL the policyholder must visit to approve the PayShap transfer

Required env vars:
  STITCH_CLIENT_ID      - your Stitch API client ID
  STITCH_CLIENT_SECRET  - your Stitch API client secret
  STITCH_API_BASE       - Stitch API base (default: https://api.stitch.money)
  STITCH_PAYSHAP_NODE   - the PayShap node id from your Stitch account
"""
import os
import json
import logging
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

STITCH_API_BASE = os.environ.get(
    "STITCH_API_BASE", "https://api.stitch.money"
)
STITCH_CLIENT_ID = os.environ.get("STITCH_CLIENT_ID", "")
STITCH_CLIENT_SECRET = os.environ.get("STITCH_CLIENT_SECRET", "")
# The PayShap node id configured in your Stitch account dashboard
STITCH_PAYSHAP_NODE = os.environ.get("STITCH_PAYSHAP_NODE", "")

# In-memory token cache (process lifetime only)
_token_cache = {"token": None, "expires_in": 0}


def is_configured():
    """Return True if the minimum Stitch credentials are present."""
    return bool(STITCH_CLIENT_ID and STITCH_CLIENT_SECRET)


def _get_access_token():
    """Exchange client credentials for an OAuth2 access token (client_credentials grant)."""
    if not is_configured():
        raise StitchError("Stitch is not configured. Set STITCH_CLIENT_ID and STITCH_CLIENT_SECRET.")

    url = f"{STITCH_API_BASE}/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": STITCH_CLIENT_ID,
        "client_secret": STITCH_CLIENT_SECRET,
        "scope": "client_paymentinitiation",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = requests.post(url, data=payload, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise StitchError(f"Stitch token request failed ({resp.status_code}): {resp.text[:200]}")

    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise StitchError("Stitch token response did not contain access_token.")

    _token_cache["token"] = token
    _token_cache["expires_in"] = data.get("expires_in", 3600)
    return token


def _graphql_query(query, variables=None):
    """Execute a GraphQL query against the Stitch API."""
    token = _token_cache.get("token") or _get_access_token()
    url = f"{STITCH_API_BASE}/graphql"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {"query": query}
    if variables:
        body["variables"] = variables

    resp = requests.post(url, json=body, headers=headers, timeout=30)
    if resp.status_code == 401:
        # Token expired — refresh and retry once
        _token_cache["token"] = None
        token = _get_access_token()
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.post(url, json=body, headers=headers, timeout=30)

    if resp.status_code != 200:
        raise StitchError(f"Stitch GraphQL request failed ({resp.status_code}): {resp.text[:200]}")

    data = resp.json()
    if data.get("errors"):
        messages = "; ".join(e.get("message", "") for e in data["errors"])
        raise StitchError(f"Stitch GraphQL error: {messages}")
    return data.get("data", {})


def create_payshap_payment(*, amount, reference, payer_reference, beneficiary_reference,
                           external_reference, node_id=None):
    """Create a PayShap payment intent via Stitch.

    Returns a dict with:
      - payment_id:  the Stitch payment id
      - redirect_url: URL the user must visit to approve the PayShap transfer
      - status:      initial status from Stitch
    """
    amount_cents = int((Decimal(str(amount)) * Decimal("100")).to_integral_value())
    node = node_id or STITCH_PAYSHAP_NODE
    if not node:
        raise StitchError("STITCH_PAYSHAP_NODE is not set. Find the PayShap node id in your Stitch dashboard.")

    mutation = """
    mutation CreatePayShapPayment($input: ClientPaymentInitiationRequestInput!) {
      clientPaymentInitiationRequestCreate(input: $input) {
        paymentInitiationRequest {
          id
          status
          url
        }
        errors { field messages }
      }
    }
    """
    variables = {
        "input": {
            "channel": "payshap",
            "nodeId": node,
            "amount": str(amount_cents),
            "currency": "ZAR",
            "reference": reference,
            "payerReference": payer_reference,
            "beneficiaryReference": beneficiary_reference,
            "externalReference": external_reference,
            "timeoutSeconds": 600,
        }
    }

    data = _graphql_query(mutation, variables)
    result = data.get("clientPaymentInitiationRequestCreate", {})
    errors = result.get("errors")
    if errors:
        msg = "; ".join(f"{e.get('field')}: {', '.join(e.get('messages', []))}" for e in errors)
        raise StitchError(f"Stitch rejected the payment request: {msg}")

    payment = result.get("paymentInitiationRequest", {})
    if not payment:
        raise StitchError("Stitch did not return a payment initiation request.")

    return {
        "payment_id": payment.get("id"),
        "redirect_url": payment.get("url"),
        "status": payment.get("status"),
    }


def get_payment_status(stitch_payment_id):
    """Query the current status of a Stitch payment initiation request."""
    query = """
    query PaymentStatus($id: ID!) {
      clientPaymentInitiationRequest(id: $id) {
        id
        status
        amount { quantity currency }
        reference
      }
    }
    """
    data = _graphql_query(query, {"id": stitch_payment_id})
    return data.get("clientPaymentInitiationRequest", {})


class StitchError(Exception):
    pass
