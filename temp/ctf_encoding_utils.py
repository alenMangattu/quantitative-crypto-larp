from eth_abi import encode
from eth_utils import keccak


def parse_units(value: str, decimals: int) -> int:
    return int(float(value) * (10**decimals))


def function_selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def encode_ctf_call(
    function_signature: str,
    usdc_address: str,
    parent_id: bytes,
    condition_id: bytes,
    amount: int,
) -> bytes:
    selector = function_selector(function_signature)
    args = encode(
        ["address", "bytes32", "bytes32", "uint256[]", "uint256"],
        [usdc_address, parent_id, condition_id, [0, 1], amount],
    )
    return selector + args
