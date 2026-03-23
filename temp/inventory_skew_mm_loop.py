import math
import time

# Strategy parameters
kappa = 0.1  # Inventory skew factor
spread0 = 0.02  # Base spread (2%)
tick_size = 0.01  # Minimum price increment
max_allowed = 500  # Max inventory limit


def round_down(price: float, step: float) -> float:
    return math.floor(price / step) * step


def round_up(price: float, step: float) -> float:
    return math.ceil(price / step) * step


def market_maker_loop(token_id, n_limit):
    while True:
        # 1. Collect market data
        best_bid, best_ask = get_orderbook_top(token_id)
        mid = (best_bid + best_ask) / 2

        # 2. Check current inventory (net YES position)
        n = check_inventory(token_id)

        # 3. Calculate inventory skew
        delta = kappa * n

        # 4. Compute bid/ask prices
        price_bid = mid - spread0 / 2 + delta
        price_ask = mid + spread0 / 2 + delta

        # 5. Round to tick size
        price_bid = round_down(price_bid, tick_size)
        price_ask = round_up(price_ask, tick_size)

        # 6. Determine order size (Kelly-based sizing)
        size = calculate_order_size(n)

        # 7. Submit post-only orders
        post_order("BUY", price_bid, size, "POST_ONLY")
        post_order("SELL", price_ask, size, "POST_ONLY")

        # 8. Process executions
        executions = fetch_my_fills()
        update_inventory(n, executions)

        # 9. Hedge if necessary
        if abs(n) > max_allowed:
            if n > 0:
                post_market_order("SELL", n - n_limit, mid)
            else:
                post_market_order("BUY", abs(n) - n_limit, mid)

        time.sleep(1)
