"""Era citation bind enforcer — full law."""
class EraBinder:
    def bind(self, card: dict) -> dict:
        card["era_bind"] = "HOUSE_ERA"
        card["citation"] = "GB-15"
        card["stored_prose"] = 0
        return card
