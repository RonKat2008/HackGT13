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
