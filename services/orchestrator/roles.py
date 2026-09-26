from uuid import uuid4

from models import Claim, Patch, PatchKind, PatchStatus, Product

_FALLBACK_BODY = "{metric} results"
_FALLBACK_PATCH_TEXT = "Search the results section for the metric."


def critic(
    claim: Claim,
    verdict_label: str,
    allow_list: list[str],
    model_json: dict | None = None,
) -> Patch:
    if not allow_list:
        raise ValueError("allow_list must contain at least one specialist")

    if allow_list[0] == "evidence":
        window = "neighbors:2"
        if model_json is not None and model_json.get("body") in {"neighbors:1", "neighbors:2"}:
            window = model_json["body"]
        return Patch(
            id=uuid4(),
            product=Product.ARXAUDIT,
            kind=PatchKind.SPAN_WINDOW,
            target="evidence",
            trigger=verdict_label,
            body=window,
            patch_text="Widen the evidence window around the claim.",
            status=PatchStatus.DRAFT,
            wins=0,
            losses=0,
            fitness_ema=0.0,
            uses=0,
        )

    body = _FALLBACK_BODY
    patch_text = _FALLBACK_PATCH_TEXT
    if model_json is not None:
        candidate = model_json.get("body", "")
        if "{" in candidate:
            body = candidate
            patch_text = model_json.get("patch_text", _FALLBACK_PATCH_TEXT)

    return Patch(
        id=uuid4(),
        product=Product.STORMCITE,
        kind=PatchKind.QUERY_TEMPLATE,
        target=allow_list[0],
        trigger=verdict_label,
        body=body,
        patch_text=patch_text,
        status=PatchStatus.DRAFT,
        wins=0,
        losses=0,
        fitness_ema=0.0,
        uses=0,
    )
