# FAANG Index — FastAPI REST API

A standalone Python project. It does not depend on the calculator or LinkedIn application. This is your custom index name, not the five-stock FAANG basket or an official S&P product.

For a free public HTTPS address on Render, follow [DEPLOY.md](DEPLOY.md). The included `render.yaml` selects the Free plan and protects refresh calls with a generated secret. Local unauthenticated operation is allowed only when no refresh token is set and neither cloud mode nor required-token mode is enabled.

## Start and call it from your phone

Application code lives in `src/faang_index_api/`, and tests live in `tests/`. The README, `.gitignore`, `requirements.txt`, `pyproject.toml`, launch scripts and Render configuration stay at the project root. Dependencies are declared in `pyproject.toml`; `requirements.txt` installs the project in editable mode so package imports work in development and deployment. Runtime output and caches remain in the ignored root `data/` folder.

```powershell
cd C:\Users\zhang\Git_projects\faang_index_api
powershell -ExecutionPolicy Bypass -File .\Setup.ps1
powershell -ExecutionPolicy Bypass -File .\Start.ps1
```

Open the printed `http://<PC-IP>:8002/docs` on a phone connected to the same Wi-Fi. Select an endpoint, **Try it out**, then **Execute**. On this PC use `http://localhost:8002/docs`. The root URL redirects to these interactive API docs. Keep the terminal open; Ctrl+C stops the server. Windows Firewall must allow Python from your trusted network. This unauthenticated learning server is for a trusted LAN, not public internet hosting.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Server health |
| GET | `/api/demo` | Fully calculated example using fictional stocks, explicitly labelled |
| POST | `/api/refresh?year=2026` | Download data and rebuild the live index in a background job |
| GET | `/api/refresh/status` | Job progress or actionable failure |
| GET | `/api/index?year=2026` | Last successful live result, full daily series and next-session holdings |

Omit `year` to use the current year in Europe/London. Returns are decimal fractions: `0.01` means 1%. Every live response includes `as_of`, `fetched_at` and `served_at`; cached data is not presented as today's fresh data. Request a refresh after each market close to update it. Daily rebalancing describes the calculation, not an installed scheduler. No transactions are placed.

## Data provider: Financial Modeling Prep

Provider documentation: https://site.financialmodelingprep.com/developer/docs

FMP documents current S&P 500 constituents, historical changes, company profiles, historical market caps and split-adjusted historical prices. **A provider account/API key with access to all these endpoints is required. Live integration cannot be verified without one.** Do not assume a free plan covers this workload; verify endpoint entitlements, daily history, call limits and licensing with FMP before paying. No subscription or account was created by this project.

Set the key only in the PowerShell terminal where you launch the server:

```powershell
$env:FMP_API_KEY = 'your-key'
.\Start.ps1
```

Then POST `/api/refresh`, poll `/api/refresh/status`, and GET `/api/index` after completion. A first refresh can use roughly 1,500+ requests and take several minutes: profiles, prices and caps for every company eligible during the year. Successful provider responses are cached per UTC date under ignored `data/provider_cache/`. A provider failure preserves the last good index; retry after resolving it. No key is stored in cache files or returned in responses. With no key, the demo works and live endpoints report HTTP 503 rather than invent data.

The adapter expects FMP's documented membership-change fields (`date`, `symbol`, `addedSecurity`, `removedTicker`), profile `cik`/`currency`, market-cap `marketCap`, and price `close`. Provider schema, incomplete membership events, delisted symbols, ticker changes or missing daily records can prevent a refresh. Current company identity mappings are used for share-class deduplication; complex historical restructurings require audited identity data. Membership reconstruction depends on the provider's history being complete and its dates being effective dates. Numerical checks cannot certify that history. Verify the adapter with real entitled responses before relying on live results.

EODHD was also checked; its documented stock historical market-cap series is **weekly**, so it does not directly satisfy daily market-cap rebalancing: https://eodhd.com/financial-apis/historical-market-capitalization-api

## Index methodology

- Start at **100 at the close of the first NYSE trading session of the year**. January 1 is not a trading session; with this convention the first trading day's return is excluded. For 2026 the base session is January 2.
- Use only completed NYSE sessions, including holiday and early-close rules. Intraday quotes are excluded. Weekends return the most recent completed session after refresh.
- Reconstruct the S&P 500 membership at each historical close by reversing subsequent additions/removals from current membership. Do not simply use today's top 10 for the whole year.
- Each close, select the ten distinct eligible companies with largest reported USD company market caps. Deduplicate share classes by CIK, choose the alphabetically first eligible ticker as the investable representative, and do not sum repeated company caps. This rule avoids counting Alphabet twice. The result includes each representative symbol and company ID.
- For each selected company, `weight = market_cap / sum(selected_market_caps)`.
- The following session earns `daily_return = sum(previous_close_weight * (current_split_adjusted_close / previous_close - 1))`.
- Compound `index_level = previous_level * (1 + daily_return)`. Year-to-date growth is `index_level / 100 - 1`.
- The latest `next_session_holdings` are selected at the latest close; `history[].contributions` shows the prior-close holdings that actually earned each day's return.
- This is a **price-return** index: dividends, transaction costs, taxes, trading impact and free-float adjustments are excluded. Prices are split adjusted, market caps are provider-reported daily values. Caps and prices for every eligible constituent must be present on each session; held names also need a price when they exit. Missing records are errors, never forward-filled caps or zero returns.

The optional year parameter is bounded by the installed exchange calendar's coverage. Live provider results may require additional historical identity handling for older years. The demo has only three synthetic sessions and never claims to be market performance.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Tests cover compounding, prior-day selection, membership changes, share-class deduplication, invalid data, missing held prices, exchange holidays, demo/live separation and refresh persistence. Network-free tests use synthetic fixtures and mocked provider calls; they do not verify a real FMP account or phone firewall access.
