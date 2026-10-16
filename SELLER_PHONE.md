# Seller Mini Program phone preview

Status on 16 October 2026: the official DevTools preview command generated a
26,726-byte Mini Program preview and its QR code for `wx8cb01bd3c9f16e2a`
(卖家智能X助手). No release or experience-version upload was performed.
The user opened this preview on a phone and generated a valid WeChat linking
request. That request was successfully approved for the existing demo seller.
The user confirmed that both product and order lists display on the phone.
Phone-preview and write-flow acceptance passed. All four final confirmations
were made on the owner's phone and audited as real WeChat actions.

## Connection status and completed acceptance

- The corrected server AppSecret passed an actual `jscode2session` exchange
  using a real DevTools `wx.login` code. The backend returned 200 and a WeChat
  session. The diagnostic session was then revoked without binding an account.
- The user saved the request-domain configuration. The phone subsequently
  reached the backend and produced a valid authenticated linking request.
  The generated client continues to have `urlCheck` enabled.
- The phone's request was approved through the normal website-authenticated
  API with its matching six-character code. The API confirmed `mode=wechat`
  and linkage to `seller@atelierform.test`, with its existing products and orders (counts increase during acceptance).
- The user selected **Refresh connection**, **My products** and **My orders**
  and confirmed that both lists display on the phone. The owner subsequently
  confirmed stock 7 -> 9, price 20 -> 25.50, an unpublished listing and a
  simulated paid order's shipment. All four are applied with confirmation
  channel `wechat`; actual database values were independently verified.

The current temporary origin is
`https://beans-summaries-brilliant-labs.trycloudflare.com`.
It depends on this computer and its tunnel remaining running. Restarting a
temporary tunnel normally assigns another origin: update the request-domain
allowlist, regenerate the phone project, and generate another QR. This is not
a permanent public deployment.

## Server and client preparation

Create `.seller-agent-runtime/wechat-secrets.env` locally, outside Git:

```dotenv
WECHAT_APP_ID=wx8cb01bd3c9f16e2a
WECHAT_APP_SECRET=replace-locally-with-the-current-AppSecret
```

Never put the secret into Mini Program files, source archives or chat. The
generated phone project contains only the AppID, HTTPS API URL and client code.

Start an HTTPS reverse proxy/tunnel to `http://127.0.0.1:8781`. On the prepared
computer the tunnel executable is `D:\CodexWork\DIP\runtime\cloudflared.exe`.
Then run from this repository using the existing Python environment:

```powershell
& '..\runtime\venv\Scripts\python.exe' run_seller_phone.py --env-file '..\dip-new-repo-test\.env' --origin 'https://YOUR-APPROVED-HOST'
```

This generates `.seller-agent-runtime/phone-miniprogram` with real WeChat login
and domain checks enabled. Open that directory in WeChat DevTools and use
Preview to generate the official QR. The source `miniprogram` remains the
separate local-development configuration.

To stop only the phone backend, create `.seller-agent-runtime/stop-8781`.
Restart the command above after changing credentials. Keep the tunnel running
if retaining its current address. The local developer server at port 8780 is
independent.

## What is verified

- HTTPS requests, static assets and authenticated seller website login pass.
- Public developer login is denied; unauthenticated private data is denied.
- Admin, checkout and local browser-preview routes are not exposed on this host.
- The original 27 seller-agent/phone checks passed; see the final delivery report
  for the expanded regression after editor and upload fixes.
- A real `wx.login` code was obtained from DevTools. Official code exchange
  passed after correcting the credential; the returned identity was unlinked.
  This verifies the server integration, not client-domain access or phone use.
- The original official QR was scanned successfully on the user's phone.
  Later QR refresh attempts initially failed with `socket hang up` and
  `APPID_ERROR`. After developer re-login, a new official QR was successfully
  generated at 22:44 China time on 16 October 2026 (20,471-byte client).
- Real phone account linking, product/order list display and the four core
  write confirmations passed. Preview preparation is shared with the website;
  phone confirmations and resulting database state were verified. This does
  not establish production release readiness or untested bulk operations.

The phone host includes the seller assistant, secure linking and authenticated
product editing, photo upload, options and publication. It reuses the existing
seller forms, models and ownership rules.
No real WeChat Pay, payment capture or automatic product publication is added.

## Portable launchers

`START-SELLER-PHONE.cmd --origin https://YOUR-APPROVED-HOST` starts the phone
backend using the same configured database. On this prepared machine it can
reuse the saved origin. `STOP-SELLER-PHONE.cmd` stops only that backend, leaving
the tunnel intact. Neither command uploads or publishes the Mini Program.
