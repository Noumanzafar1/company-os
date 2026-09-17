"""Synthetic source fixtures. No network, inferred facts or real identities."""


class FakeSourceProvider:
    @staticmethod
    def facts(industry: str) -> list[tuple[str, str, str | bool]]:
        if industry not in {"synthetic_services", "synthetic_excluded"}:
            raise ValueError("Only registered synthetic source fixtures are supported")
        return [
            ("industry_code", "string", industry),
            ("country_code", "string", "US"),
            ("problem", "boolean", True),
            ("deal_capacity", "boolean", True),
            ("observed_trigger", "boolean", True),
        ]
