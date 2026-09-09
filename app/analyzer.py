"""Decode and score common EVM transaction patterns without signing or sending."""

from __future__ import annotations

from dataclasses import dataclass

UINT256_MAX = 2**256 - 1


@dataclass(frozen=True)
class DecodedCall:
    function: str
    arguments: dict[str, str | bool]


def _word(data: str, index: int) -> str | None:
    start = 8 + index * 64
    value = data[start : start + 64]
    return value if len(value) == 64 else None


def _address(word: str) -> str:
    return "0x" + word[-40:]


def decode_call(calldata: str) -> DecodedCall | None:
    data = calldata.removeprefix("0x").lower()
    if len(data) < 8:
        return None

    selector = data[:8]
    first, second, third = _word(data, 0), _word(data, 1), _word(data, 2)

    if selector == "a9059cbb" and first and second:
        return DecodedCall("transfer(address,uint256)", {
            "recipient": _address(first), "amount_raw": str(int(second, 16))
        })
    if selector == "095ea7b3" and first and second:
        amount = int(second, 16)
        return DecodedCall("approve(address,uint256)", {
            "spender": _address(first),
            "amount_raw": str(amount),
            "unlimited": amount == UINT256_MAX,
        })
    if selector == "23b872dd" and first and second and third:
        return DecodedCall("transferFrom(address,address,uint256)", {
            "sender": _address(first),
            "recipient": _address(second),
            "amount_raw": str(int(third, 16)),
        })
    if selector == "a22cb465" and first and second:
        return DecodedCall("setApprovalForAll(address,bool)", {
            "operator": _address(first), "approved": bool(int(second, 16))
        })
    return DecodedCall("unknown", {"selector": "0x" + selector})


def risk_assessment(
    decoded: DecodedCall | None,
    simulation_ok: bool,
    target_is_contract: bool,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    score = 0

    if not simulation_ok:
        warnings.append("Simulation reverted; do not submit this transaction as-is.")
        score += 100
    if decoded and decoded.function == "approve(address,uint256)":
        if decoded.arguments.get("unlimited"):
            warnings.append("Unlimited token approval grants the spender maximum allowance.")
            score += 80
        else:
            warnings.append("This transaction grants a token allowance to a spender.")
            score += 25
    if decoded and decoded.function == "setApprovalForAll(address,bool)" and decoded.arguments.get("approved"):
        warnings.append("This grants an operator control over all assets in the collection.")
        score += 80
    if decoded and decoded.function == "unknown" and target_is_contract:
        warnings.append("Unknown contract function; inspect the target and calldata manually.")
        score += 35

    if score >= 80:
        return "dangerous", warnings
    if score:
        return "warning", warnings
    return "safe", warnings

