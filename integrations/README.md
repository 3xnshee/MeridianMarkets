# Private integration boundary

Meridian Markets is designed to stay fully functional without any private trading or wallet service.

## Public app responsibilities
- Dashboard UI
- Market data display
- Watchlists and local state
- Desktop packaging and launch flow
- Optional feature tabs that remain safe when disconnected

## Private service responsibilities
- Authentication and authorization
- Trading actions and order routing
- Wallet/balance access
- Transaction history
- Secrets, tokens, and custody-sensitive logic

## Contract expected by the public app
The public build expects a provider object at `window.MERIDIAN_PRIVATE_PROVIDER`.
If it is not present, the app falls back to the no-op provider in `private/provider.js`.

Recommended provider methods:
- `getStatus()` -> `{ connected, authorized, accountName, institution }`
- `connect()` -> starts an auth flow or returns a connection URL
- `getAccountSummary()` -> balances and buying power
- `getWalletSummary()` -> wallet state
- `placeOrder(order)` -> submit a trade order
- `listTransactions()` -> recent activity

## Recommended private endpoints
If you prefer HTTP instead of an in-page provider, keep the same contract and expose it behind a private backend, for example:
- `GET /api/private/status`
- `POST /api/private/connect`
- `GET /api/private/account-summary`
- `GET /api/private/wallet-summary`
- `POST /api/private/orders`
- `GET /api/private/transactions`

## Public-build behavior when disconnected
- Trading and Wallet tabs remain visible but show a locked / disconnected message
- The dashboard keeps working normally
- No account or wallet data is required for basic use
- No private dependency is needed to run the open-source build
