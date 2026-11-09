"""Rights-readiness audit, separate from byte integrity or gameplay quality."""
from ..security.rights import AssetRights, admit
from ..contracts.errors import AuthorizationError

def evaluate(assets: list[AssetRights]) -> dict:
    denied = []
    for index, asset in enumerate(assets):
        try:
            admit(asset, redistribution=True)
        except AuthorizationError:
            denied.append(index)
    return {'status': 'pass' if not denied else 'fail', 'denied_assets': denied, 'license_review_attested': False}
