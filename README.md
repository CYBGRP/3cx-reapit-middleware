# 3CX Reapit Middleware

Middleware API that connects 3CX CRM integration to Reapit.

## Current working MVP

- 3CX contact lookup by phone number
- Reapit contact search using the sandbox customer `SBOX`
- 3CX call journaling
- Reapit journal entry creation using `typeId: PH`

## Hosted URL

https://king-prawn-app-zvcjx.ondigitalocean.app

## Endpoints

Health check:

GET /health

Contact lookup:

GET /api/3cx/reapit/lookup?number=07890123456

Call log:

POST /api/3cx/reapit/call-log

## Required environment variables

REAPIT_CLIENT_ID=
REAPIT_CLIENT_SECRET=
REAPIT_CUSTOMER_ID=SBOX
REAPIT_API_VERSION=2020-01-31
REAPIT_TOKEN_URL=https://connect.reapit.cloud/token
REAPIT_BASE_URL=https://platform.reapit.cloud
THREECX_API_KEY=

## 3CX setup

Upload `ReapitMiddleware.xml` into 3CX CRM Integration.

Use:

- Query CRM: Always query
- Middleware API Key: private middleware API key
- Enable Call Journaling: enabled

## Notes

Do not commit `.env` or real secrets.
Before using this against a live Reapit customer, rotate the Reapit client secret.