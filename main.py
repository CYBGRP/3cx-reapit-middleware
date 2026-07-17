import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


load_dotenv()

app = FastAPI(title="3CX to Reapit Middleware")

REAPIT_CLIENT_ID = os.getenv("REAPIT_CLIENT_ID")
REAPIT_CLIENT_SECRET = os.getenv("REAPIT_CLIENT_SECRET")
REAPIT_CUSTOMER_ID = os.getenv("REAPIT_CUSTOMER_ID", "SBOX")
REAPIT_API_VERSION = os.getenv("REAPIT_API_VERSION", "2020-01-31")
REAPIT_TOKEN_URL = os.getenv("REAPIT_TOKEN_URL", "https://connect.reapit.cloud/token")
REAPIT_BASE_URL = os.getenv("REAPIT_BASE_URL", "https://platform.reapit.cloud")
THREECX_API_KEY = os.getenv("THREECX_API_KEY")
THREECX_BASE_URL = os.getenv("THREECX_BASE_URL", "").rstrip("/")
THREECX_CALL_CONTROL_CLIENT_ID = os.getenv("THREECX_CALL_CONTROL_CLIENT_ID")
THREECX_CALL_CONTROL_CLIENT_SECRET = os.getenv("THREECX_CALL_CONTROL_CLIENT_SECRET")

_threecx_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


class CallLogRequest(BaseModel):
    associatedId: str
    number: Optional[str] = None
    direction: Optional[str] = None
    agent: Optional[str] = None
    duration: Optional[str] = None
    summary: Optional[str] = None
    transcript: Optional[str] = None


class ClickToDialRequest(BaseModel):
    extension: str
    number: str


def check_api_key(x_3cx_api_key: Optional[str]) -> None:
    if not THREECX_API_KEY:
        raise HTTPException(status_code=500, detail="THREECX_API_KEY is not set on the server")

    if x_3cx_api_key != THREECX_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid 3CX API key")


def get_threecx_token() -> str:
    now = time.time()

    if _threecx_token_cache["access_token"] and _threecx_token_cache["expires_at"] > now + 60:
        return _threecx_token_cache["access_token"]

    if not THREECX_BASE_URL:
        raise HTTPException(status_code=500, detail="THREECX_BASE_URL is not set")
    if not THREECX_CALL_CONTROL_CLIENT_ID:
        raise HTTPException(status_code=500, detail="THREECX_CALL_CONTROL_CLIENT_ID is not set")
    if not THREECX_CALL_CONTROL_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="THREECX_CALL_CONTROL_CLIENT_SECRET is not set")

    response = requests.post(
        f"{THREECX_BASE_URL}/connect/token",
        auth=(THREECX_CALL_CONTROL_CLIENT_ID, THREECX_CALL_CONTROL_CLIENT_SECRET),
        data={
            "client_id": THREECX_CALL_CONTROL_CLIENT_ID,
            "client_secret": THREECX_CALL_CONTROL_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"3CX token request failed: {response.status_code} {response.text}",
        )

    token_data = response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        raise HTTPException(status_code=502, detail="3CX token response did not include access_token")

    _threecx_token_cache["access_token"] = access_token
    _threecx_token_cache["expires_at"] = now + int(token_data.get("expires_in", 3600))
    return access_token


def get_reapit_token() -> str:
    now = time.time()

    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    if not REAPIT_CLIENT_ID or not REAPIT_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Reapit Client ID or Client Secret is missing")

    response = requests.post(
        REAPIT_TOKEN_URL,
        auth=(REAPIT_CLIENT_ID, REAPIT_CLIENT_SECRET),
        data={
            "grant_type": "client_credentials",
            "client_id": REAPIT_CLIENT_ID,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Reapit token: {response.status_code} {response.text}",
        )

    token_data = response.json()

    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + int(token_data.get("expires_in", 3600))

    return _token_cache["access_token"]


def reapit_headers() -> dict:
    token = get_reapit_token()

    return {
        "Authorization": f"Bearer {token}",
        "reapit-customer": REAPIT_CUSTOMER_ID,
        "api-version": REAPIT_API_VERSION,
        "Content-Type": "application/json",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "3CX to Reapit Middleware",
        "customer": REAPIT_CUSTOMER_ID,
        "clickToDialConfigured": bool(
            THREECX_BASE_URL
            and THREECX_CALL_CONTROL_CLIENT_ID
            and THREECX_CALL_CONTROL_CLIENT_SECRET
        ),
    }


@app.post("/api/3cx/click-to-dial")
def click_to_dial(
    request_data: ClickToDialRequest,
    x_3cx_api_key: Optional[str] = Header(default=None),
):
    check_api_key(x_3cx_api_key)

    extension = request_data.extension.strip()
    number = request_data.number.strip()

    if not extension.isdigit():
        raise HTTPException(status_code=422, detail="extension must contain digits only")
    if not number:
        raise HTTPException(status_code=422, detail="number is required")

    token = get_threecx_token()
    response = requests.post(
        f"{THREECX_BASE_URL}/callcontrol/{extension}/makecall",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"destination": number},
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"3CX click-to-dial failed: {response.text}",
        )

    response_payload = None
    if response.text:
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = response.text

    return {
        "ok": True,
        "message": "3CX click-to-dial request accepted",
        "extension": extension,
        "number": number,
        "threecxResponse": response_payload,
    }


@app.post("/api/3cx/reapit/call-log")
def create_call_log(
    call: CallLogRequest,
    x_3cx_api_key: Optional[str] = Header(default=None),
):
    check_api_key(x_3cx_api_key)

    description = f"""3CX Call Log

Direction: {call.direction or "Unknown"}
Number: {call.number or "Unknown"}
Agent: {call.agent or "Unknown"}
Duration: {call.duration or "Unknown"}

Summary:
{call.summary or "No summary provided."}

Transcript:
{call.transcript or "No transcript provided."}
"""

    journal_payload = {
        "associatedType": "contact",
        "associatedId": call.associatedId,
        "typeId": "PH",
        "description": description,
    }

    response = requests.post(
        f"{REAPIT_BASE_URL}/journalEntries",
        headers=reapit_headers(),
        json=journal_payload,
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Reapit journal entry failed: {response.text}",
        )

    return {
        "ok": True,
        "message": "Reapit journal entry created",
        "associatedId": call.associatedId,
        "typeId": "PH",
    }

def normalise_phone(value: Optional[str]) -> str:
    if not value:
        return ""

    digits = "".join(ch for ch in value if ch.isdigit())

    # Convert UK international format 447890123456 to 07890123456
    if digits.startswith("44") and len(digits) >= 12:
        digits = "0" + digits[2:]

    # Convert 00447890123456 to 07890123456
    if digits.startswith("0044"):
        digits = "0" + digits[4:]

    return digits


def contact_matches_number(contact: dict, number: str) -> bool:
    target = normalise_phone(number)

    possible_numbers = [
        contact.get("mobilePhone"),
        contact.get("homePhone"),
        contact.get("workPhone"),
    ]

    for phone in possible_numbers:
        if normalise_phone(phone) == target:
            return True

    return False


@app.get("/api/3cx/reapit/lookup")
def lookup_contact(
    number: str,
    x_3cx_api_key: Optional[str] = Header(default=None),
):
    check_api_key(x_3cx_api_key)

    # MVP: check the first few pages of contacts.
    # This is fine for sandbox testing.
    # Later we will replace this with a proper local cache.
    for page_number in range(1, 6):
        response = requests.get(
            f"{REAPIT_BASE_URL}/contacts",
            headers=reapit_headers(),
            params={
                "pageSize": 100,
                "pageNumber": page_number,
            },
            timeout=30,
        )

        if not response.ok:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Reapit contact lookup failed: {response.text}",
            )

        data = response.json()
        contacts = data.get("_embedded", [])

        for contact in contacts:
            if contact_matches_number(contact, number):
                first_name = contact.get("forename") or ""
                last_name = contact.get("surname") or ""
                full_name = f"{first_name} {last_name}".strip()

                return {
                    "found": True,
                    "id": contact.get("id"),
                    "entityType": "contact",
                    "firstName": first_name,
                    "lastName": last_name,
                    "fullName": full_name,
                    "phone": contact.get("mobilePhone") or contact.get("homePhone") or contact.get("workPhone"),
                    "email": contact.get("email"),
                }

    return {
        "found": False,
        "number": number,
        "message": "No matching Reapit contact found",
    }