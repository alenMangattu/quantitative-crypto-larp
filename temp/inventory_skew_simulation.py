import numpy as np

# Simulation parameters
T = 1000  # Time steps
prices = np.cumsum(np.random.randn(T) * 0.005) + 0.5  # Random walk (sigma=0.005)

# Strategy state
inventory = 0
cash = 0.0
spread = 0.05  # 5% base spread
k = 0.1  # Inventory skew factor

# Trading loop
for i in range(T - 1):
    mid = prices[i]

    # Calculate quotes with inventory skew
    price_bid = mid - spread / 2 + k * inventory
    price_ask = mid + spread / 2 + k * inventory
    next_price = prices[i + 1]

    # Simulate FOK executions
    if next_price > price_ask:
        # Sell execution
        cash += price_ask
        inventory -= 1
    elif next_price < price_bid:
        # Buy execution
        cash -= price_bid
        inventory += 1

# Mark-to-market P&L
final_price = prices[-1]
pnl = cash + inventory * final_price
print(f"Final P&L: {pnl:.4f}")