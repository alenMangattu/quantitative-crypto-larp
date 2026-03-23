from eth_utils import to_hex

from ctf_encoding_utils import encode_ctf_call, parse_units


async def merge_yes_no_to_usdc(relayer_client, ctf_address, usdc_address, condition_id):
    # Merge YES/NO back to USDC
    merge_tx = {
        "to": ctf_address,
        "data": to_hex(
            encode_ctf_call(
                function_signature="mergePositions(address,bytes32,bytes32,uint256[],uint256)",
                usdc_address=usdc_address,
                parent_id=bytes(32),  # HashZero
                condition_id=condition_id,
                amount=parse_units("500", 6),
            )
        ),
        "value": 0,
    }

    await relayer_client.execute([merge_tx], "Merge Yes/No to USDC")
