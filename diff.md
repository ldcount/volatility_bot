Ok, I now have one more request for you to implement. Let it
be in the file funding_diff.py.

Goal:

Identify arbitrage opportunities by comparing funding rates between Bybit and
OKX.

Scope:

- Instruments: USDT-margined perpetual futures (linear)
- Exchanges: Bybit and OKX

As of now with the /negative or /positive commands, the app is looking for the
most negative / positive rates on Bybit and compares it with the rates on OKX
and checks if in principle the same ticker is present on OKX in the first
place.

I'd like to introduce now a new command /funding_diff what would do the
following.

I'd like to find the 30 symbols in USDT / perps sections (linear) existing
simultaneously on both exchanges and where the difference between the absolute
funding rates on both exchanges at the max. I.e. there will be the sorting
based on the max difference. If the difference is the same, the sorting shall
be done by alphabetic order. So, a list of Top 30 **after sorting by diff**irence.

If it’s possible to get a
timestamp for the funding rate, it shall be returned as well. Funding rates can
update every 8 hours (usually) or every 4, and even 1 hour. If API**s return timestamps,
this shall be in the output.**

The difference between funding rates shall be absolute: abs(funding_bybit)

- abs(funding_okx).

The symbols names have different spelling on both exchanges,
make sure they really correspond.

For example, Bybit: RAVEUSDT, but on OKX rave-usdt-swap.
Look in the libs of both exchanges to get the right notation.

The logic:

1. Fetch all USDT perpetual contracts from:

- Bybit (linear perps)
- OKX (USDT-SWAP)

2. Normalize symbols to a common format:

Example:

- BTCUSDT (Bybit)
- BTC-USDT-SWAP (OKX)

→ normalized to: BTCUSDT

3. Keep only symbols present on BOTH exchanges.
4. For each common symbol:

- Retrieve latest funding rate and timestamp (if available) from both exchanges
- Compute:

funding_diff = abs(funding_bybit) – abs(funding_okx)

5. Filter out symbols where:

- funding rate is missing on either exchange

6. Sort results:

- Primary: funding_diff (descending)
- Secondary: symbol (alphabetical ascending)

7. Select top 30 symbols after sorting.

Output format:

1/ sorting direction (descending)

2/ number formatting present

3/ message format:

Output format (Telegram message):

Form:

<symbol 1>

Diff: `<diff>` | Bybit: `<rate>` `<timestamp>` |
OKX: `<rate>` `<timestamp>`

<symbol 2>

Diff: `<diff>` | Bybit: `<rate>` `<timestamp>` |
OKX: `<rate>` `<timestamp>`

Output message example:

⚖️Funding arbitrage: ByBit – OKX (

**1. BTCUSDT**

Diff: 0.025% | 0.010% 8h | -0.015% 4h

**2. RAVEUSDT **

Diff: 0.035% | 0.010% 8h | -0.015% 1h

If timestamp is not retrievable via the lib / api, don’t put
it in the output message

Edge cases:

- Handle API errors gracefully
- Skip symbols with null funding rates
