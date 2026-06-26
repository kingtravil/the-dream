"""TAB NZ affiliate API credentials — ingestion only, no betting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TabNZConfig:
    base_url: str = "https://api.tab.co.nz/affiliates/v1"
    from_email: str = ""
    x_partner: str = ""
    x_partner_id: str = ""
    fixture_path: Path | None = None
    timeout_seconds: int = 30

    @property
    def has_credentials(self) -> bool:
        return bool(self.from_email and self.x_partner)

    @property
    def use_fixture(self) -> bool:
        return not self.has_credentials
