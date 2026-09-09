from app.analyzer import UINT256_MAX, decode_call, risk_assessment


def word(value: int) -> str:
    return f"{value:064x}"


def address_word(address: str) -> str:
    return address.removeprefix("0x").rjust(64, "0")


def test_decodes_transfer():
    recipient = "0x1111111111111111111111111111111111111111"
    decoded = decode_call("0xa9059cbb" + address_word(recipient) + word(1_500_000))
    assert decoded is not None
    assert decoded.function == "transfer(address,uint256)"
    assert decoded.arguments == {"recipient": recipient, "amount_raw": "1500000"}


def test_unlimited_approval_is_dangerous():
    spender = "0x2222222222222222222222222222222222222222"
    decoded = decode_call("0x095ea7b3" + address_word(spender) + word(UINT256_MAX))
    verdict, warnings = risk_assessment(decoded, simulation_ok=True, target_is_contract=True)
    assert verdict == "dangerous"
    assert any("Unlimited" in warning for warning in warnings)


def test_unknown_contract_call_warns():
    decoded = decode_call("0x12345678")
    verdict, warnings = risk_assessment(decoded, simulation_ok=True, target_is_contract=True)
    assert verdict == "warning"
    assert warnings


def test_plain_transfer_is_safe():
    verdict, warnings = risk_assessment(None, simulation_ok=True, target_is_contract=False)
    assert verdict == "safe"
    assert warnings == []

