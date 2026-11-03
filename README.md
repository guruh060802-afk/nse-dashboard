# NSE shortlist dashboard

A single-page dashboard that shows a short list of NSE stocks with entry, stop,
target and share quantity sized to a small account, plus live last-traded prices.

**This is a filter and a calculator, not investment advice.** No forecast, no
recommendation, no claim of an edge. I am not a registered investment adviser.

## Where the prices come from

Prices are fetched server-side by `quotes.py`, which is run every 15 minutes
during market hours by the workflow in `.github/workflows/refresh-quotes.yml`.
It writes `data/quotes.js`, and the page loads that file with a `<script>` tag.

That indirection is deliberate. A browser cannot call NSE or Yahoo directly:
NSE sends `access-control-allow-origin` for its own domain only, and Yahoo's
chart endpoint sends no CORS header at all. So the fetch happens on a server and
the result is handed to the page as a plain file.

Sources, in the order tried:

1. NSE `NextApi/GetQuoteApi` — last traded price and previous close
2. Yahoo Finance `v8/finance/chart` — fallback

The page always shows the timestamp of the data it is displaying. If
`data/quotes.js` is missing, it says so in red instead of showing old numbers.

## How current is it

Recent, not real-time. The GitHub scheduler drifts, sometimes 15 minutes or more.
Treat these as "roughly where it is trading", and confirm the price in your
broker's order screen before acting.

## Running it yourself

```
python quotes.py
```

Then open `index.html`. No build step, no dependencies beyond the Python
standard library.

## Live site

https://guruh060802-afk.github.io/nse-dashboard/
