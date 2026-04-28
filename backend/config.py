import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "Fairlytics Prototype"
    app_port: int = 8001
    min_rows_for_model: int = 50
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


settings = Settings()

THRESHOLDS = {
    "disparate_impact_low": 0.8,
    "demographic_parity_difference": 0.1,
    "equalized_odds_difference": 0.1,
    "counterfactual_flip_rate": 0.3,
}
