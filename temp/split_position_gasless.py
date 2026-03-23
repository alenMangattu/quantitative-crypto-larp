from eth_utils import to_hex

from ctf_encoding_utils import encode_ctf_call, parse_units


async def split_usdc_to_yes_no(relayer_client, ctf_address, usdc_address, condition_id):
    # Split 1000 USDC.e into YES/NO tokens
    split_tx = {
        "to": ctf_address,  # e.g. 0x4D97...
        "data": to_hex(
            encode_ctf_call(
                function_signature="splitPosition(address,bytes32,bytes32,uint256[],uint256)",
                usdc_address=usdc_address,
                parent_id=bytes(32),  # HashZero
                condition_id=condition_id,
                amount=parse_units("1000", 6),
            )
        ),
        "value": 0,
    }

    # Execute via relayer (gasless)
    await relayer_client.execute([split_tx], "Split USDC into Yes/No")
