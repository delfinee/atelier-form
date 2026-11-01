# Shared school catalogue

The Windows 1.3.2 build uses `https://dip-new-repo.vercel.app`, the original
storefront, with `mode=shared-demo`. It opens `/seller/ai/` without a login.
The Products tab reads the same `Product` rows, photographs and makers as the
public storefront. There is no catalogue import and no second database.

The shared workspace applies only to `/seller/ai/`, `/seller/products/`,
`/api/seller/products/` and `/api/seller-agent/v1/`. On the configured school
host, visitors use a request-local, unprivileged account with an unusable
password. It can manage all catalogue products. Existing product ownership
is preserved. New products belong to the dedicated School Demo maker.
The shared order list contains parcel status, purchased product names and quantities, and tracking details. Buyer names, email, phone numbers and addresses are excluded. Administration and account linking remain excluded.
Existing browser login sessions are preserved; writes still require CSRF.

`SELLER_SHARED_DEMO_HOSTS` defaults to `dip-new-repo.vercel.app`. An explicit
`SELLER_SHARED_DEMO_ENABLED=1` also enables the mode on another deployment.
To turn the school workspace off, set `SELLER_SHARED_DEMO_ENABLED=0` and
`SELLER_SHARED_DEMO_HOSTS=`. Other hosts retain the normal seller permissions.
The production Vercel build applies any missing existing `seller_agent`
migration before publishing the app. This adds the conversation/change tables;
it does not migrate or seed the product catalogue. Preview builds skip schema
changes. The dedicated account and maker are created on the first shared
workspace request; no existing rows are reassigned.

The assistant reads current products and prepares stock, price and listing
changes. The visitor must confirm each preview. New listings start as drafts;
select **Is active** in the product editor and save to publish to the storefront.
Shared-mode natural language uses DeepSeek. A server environment key takes precedence; the deployment can also read an encrypted ProviderSecret stored in the database. The encryption key is derived from the deployment secret, with SECRET_KEY_FALLBACKS supported for rotation. ProviderSecret is never exposed by an API or shipped in the Windows app.

Open seller lists poll every five seconds while visible. Public catalogue and buyer order pages check opaque revision markers and refresh when committed data changes. Active form edits are preserved. Multi-maker orders are shown as separate parcels, so confirming one shipment does not ship the other makers' items.

Build the Windows package:

```powershell
.\desktop\windows\build.ps1 -WebViewPackage <WebView2-SDK-folder> `
  -OutputDirectory <output-folder> `
  -Origin https://dip-new-repo.vercel.app -Mode shared-demo
```

Regression coverage lives in `seller_agent.test_shared_demo`: original records
across makers, stock confirmation, draft/publication visibility from a separate
visitor, ownership preservation, CSRF, unprivileged identity, unchanged buyer
sessions, and normal seller permissions on other hosts.
