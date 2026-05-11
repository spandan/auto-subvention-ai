"""Model artifact I/O and prediction helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from services.constants import ROOT


@lru_cache(maxsize=1)
def load_model() -> Any:
    path = ROOT / "model_pipeline.pkl"
    if not path.is_file():
        raise FileNotFoundError(f"Model file not found: {path}")
    import lightgbm  # noqa: F401
    from lightgbm.sklearn import LGBMClassifier  # noqa: F401

    try:
        return joblib.load(path)
    except Exception as e:
        raise RuntimeError(
            f"Could not unpickle model at {path}: {type(e).__name__}: {e}. "
            "Use compatible scikit-learn and lightgbm versions from requirements.txt."
        ) from e


def load_json(filename: str) -> dict | list | None:
    path = ROOT / filename
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_feature_schema() -> dict[str, Any]:
    data = load_json("feature_schema.json")
    if not isinstance(data, dict):
        raise ValueError(
            "feature_schema.json is missing or invalid. Expected a JSON object with "
            '"required_columns".'
        )
    cols = data.get("required_columns")
    if not isinstance(cols, list) or not cols:
        raise ValueError(
            'feature_schema.json must contain a non-empty list "required_columns".'
        )
    return data


def get_sample_defaults() -> dict[str, Any]:
    raw = load_json("sample_input.json")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("sample_input.json must be a JSON object (key → value).")
    return raw


def get_model_metadata() -> dict[str, Any] | None:
    raw = load_json("model_metadata.json")
    return raw if isinstance(raw, dict) else None


def predict_conversion(pipeline: Any, model_df: pd.DataFrame) -> float:
    if not hasattr(pipeline, "predict_proba"):
        raise AttributeError(
            "The loaded pipeline does not support predict_proba(). "
            "Use a classifier with probability estimates."
        )
    proba = pipeline.predict_proba(model_df)
    if proba.ndim != 2 or proba.shape[1] < 2:
        raise ValueError(
            f"Unexpected predict_proba output shape: {getattr(proba, 'shape', None)}"
        )
    return float(proba[0, 1])


def assert_artifacts_present() -> None:
    for name in ("model_pipeline.pkl", "feature_schema.json"):
        if not (ROOT / name).is_file():
            raise FileNotFoundError(f"Missing required file: {ROOT / name}")
