"""Immutable protocol fingerprints and chronological evaluation guards."""

import hashlib
import json
from pathlib import Path

import pandas as pd


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_protocol(path: str | Path = "configs/protocol.json") -> dict:
    config = json.loads(Path(path).read_text())
    if not (config["initial_train_end"] < config["development_start"] <=
            config["development_end"] < config["holdout_start"] <= config["holdout_end"]):
        raise ValueError("Protocol periods overlap or are reversed")
    if config["horizon_sessions"] != 20 or config["reference_session_offset"] != 2:
        raise ValueError("Version 1 requires the agreed 20-session target and two-session delay")
    return config


def write_lock(config: dict, path: str | Path) -> dict:
    lock = {"protocol_version": config["version"], "protocol_sha256": canonical_hash(config),
            "status": "primary_protocol_locked; empirical_access_gates_pending"}
    p = Path(path)
    if p.exists() and json.loads(p.read_text()) != lock:
        raise ValueError("Existing protocol lock differs; record an explicit versioned amendment")
    p.write_text(json.dumps(lock, indent=2) + "\n")
    return lock


def verify_lock(config: dict, path: str | Path) -> None:
    lock = json.loads(Path(path).read_text())
    if lock["protocol_sha256"] != canonical_hash(config):
        raise ValueError("Protocol has changed since the lock was written")


def guard_development(frame: pd.DataFrame, config: dict) -> None:
    years = pd.to_datetime(frame["acceptance_date"]).dt.year
    if (years > config["development_end"]).any():
        raise ValueError("Final-period observations are blocked from development commands")


def eligible_training(frame: pd.DataFrame, year: int, prediction_date: str) -> pd.DataFrame:
    """Labels must have ended before this year's first pre-open prediction."""
    acceptance = pd.to_datetime(frame["acceptance_date"])
    ends = pd.to_datetime(frame["label_end"])
    cutoff = pd.Timestamp(prediction_date).normalize()
    return frame.loc[(acceptance.dt.year < year) & (ends < cutoff)].copy()
