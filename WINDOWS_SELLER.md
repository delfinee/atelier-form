# Seller coursework demo: website and Windows

The English website and Windows client present one coursework demonstration.
Version 1.2.0 connects to https://demo.maijiax.cn on the Tencent server. The
developer's computer is not needed after installation; internet is required.
There is no Live shop selector, registration requirement or production setup in
the client. Each visitor gets an isolated sample shop, three products and one
simulated paid order.

The demonstration uses the existing Django services and database. DeepSeek
interprets free-form requests; exact shortcut commands query the sample records
directly. Changes require a preview and explicit confirmation. Payment and
shipping are simulated, while sample products, orders, conversations and
confirmed edits are actually saved to the demo database.

## Walkthrough

1. The Windows app opens the workspace directly. On the website, choose **Open demo**.
2. Use **My products** to inspect the sample inventory.
3. Ask for a stock or price change, then review and confirm it.
4. Use **New listing** to create an unpublished sample product; complete photos
   and options in the product editor.
5. Use **My orders**, enter a sample carrier/tracking number, and confirm a
   simulated shipment.

No real customer information should be entered. Browser/device sessions have
separate demo shops. A 24-hour session cookie does not automatically delete saved
records; the demonstration administrator controls retention.

## Run the isolated service

The hosted deployment uses `config.seller_hosted_demo` and
`deploy/hosted-demo.compose.yml`. Its PostgreSQL database and persistent volume
are separate from the original storefront. Caddy terminates HTTPS for
`demo.maijiax.cn`; the app and database expose no public ports. Its private
`deploy/.env.hosted-demo` contains the session secret, demo database password,
fixed origin and server-side DeepSeek key. Never package this file with the app.

Use a private environment file containing DATABASE_URL for a separate database
named atelier_public_demo, a random DJANGO_SECRET_KEY of at least 50 characters,
PAYMENT_PROVIDER=mock, and optionally SELLER_AGENT_USE_LLM=1 plus a server-side
SELLER_AGENT_API_KEY. The demo settings refuse other database names.

    python run_seller_web_demo.py --env-file D:\private\seller-demo.env --prepare
    python run_seller_web_demo.py --env-file D:\private\seller-demo.env --local-http --port 8784

For an HTTPS tunnel, omit --local-http and serve port 8783. The listener binds
only to 127.0.0.1 and trusts X-Forwarded-Proto only from that address. Cookies
remain Secure behind HTTPS. A temporary tunnel requires its host to remain
online. This does not deploy anything to the production host.

## Build Windows x64

Requires .NET Framework 4.8, PowerShell and Microsoft's Microsoft.Web.WebView2
NuGet SDK 1.0.4314.35 extracted to an external build directory. Official package
SHA-256: 90778DEB1B77E36292828B4B5833C9255C27533F40E0DDD55891AE718944EDC4.

    .\desktop\windows\build.ps1 -WebViewPackage D:\build\webview2-1.0.4314.35 -OutputDirectory D:\build\release -DemoOrigin https://YOUR-DEMO-HOST

Outputs include a Setup executable and a portable ZIP. The installer supports a
user-selected empty directory and an optional desktop shortcut. The client
contains only the demo origin, never a provider key, password or database
connection. It requires an online service and has no offline stock writes.

The client uses WebView2, keeps per-origin profiles, blocks cross-origin embedded
navigation, and disables host-object and web-message bridges. The original
authenticated backend routes and ownership/confirmation checks remain in the
repository; the coursework client does not expose a live-business mode.

This is an unsigned project build. It is not published in Microsoft Store.
SDK documentation: https://learn.microsoft.com/microsoft-edge/webview2/get-started/winforms
