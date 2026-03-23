from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY


def main():
    # Initialize client
    client = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,
    )

    # Create and post order
    order_args = OrderArgs(
        token_id="0x123...tokenID",
        price=0.50,
        size=100,
        side=BUY,
    )
    order = client.create_and_post_order(
        order_args=order_args,
        options={
            "tick_size": "0.01",
            "neg_risk": False,
        },
    )
    print(f"Order ID: {order.order_id}")
