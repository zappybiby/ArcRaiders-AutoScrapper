from __future__ import annotations

import re

ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
ROMAN_REGEX = re.compile(r"^(.+?)[_-]([ivx]+)$", re.IGNORECASE)


class WeaponGrouper:
    """Utility for working with weapon variants (I, II, III, ...)."""

    @staticmethod
    def get_tier_number(item_id: str) -> int:
        match = ROMAN_REGEX.match(item_id)
        if not match:
            return 0
        roman_numeral = match.group(2).upper()
        try:
            return ROMAN_NUMERALS.index(roman_numeral) + 1
        except ValueError:
            return 0

    @staticmethod
    def is_weapon_variant(item: dict) -> bool:
        item_id = str(item.get("id", ""))
        return bool(ROMAN_REGEX.match(item_id))

    @staticmethod
    def get_base_id(item_id: str) -> str:
        match = ROMAN_REGEX.match(item_id)
        return match.group(1) if match else item_id

    @staticmethod
    def get_base_name(name: str) -> str:
        return re.sub(r"\s+[IVX]+$", "", name, flags=re.IGNORECASE).strip()
