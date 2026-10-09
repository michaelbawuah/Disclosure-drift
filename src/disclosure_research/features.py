"""Train-only text vocabulary and deterministic annual change measures."""

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from .extraction import TOKEN

FEATURE_NAMES = ["log_length_change", "jaccard_distance", "tfidf_cosine_distance"]


class TextChangeFeatures:
    def __init__(self, max_features: int = 20000):
        self.vectorizer = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)\b[a-zA-Z]{2,}\b",
                                         max_features=max_features, min_df=1, ngram_range=(1, 1))
        self.fitted = False

    @staticmethod
    def _validate(pairs: pd.DataFrame):
        for column in ["previous_text", "current_text"]:
            if column not in pairs or pairs[column].isna().any():
                raise ValueError(f"Missing text column or values: {column}")
            if any(not TOKEN.findall(t) for t in pairs[column]):
                raise ValueError("Empty or untokenizable disclosure text")

    def fit(self, training_pairs: pd.DataFrame):
        self._validate(training_pairs)
        self.vectorizer.fit(training_pairs["previous_text"].tolist() +
                            training_pairs["current_text"].tolist())
        self.fitted = True
        return self

    def transform(self, pairs: pd.DataFrame) -> pd.DataFrame:
        if not self.fitted:
            raise ValueError("Fit vocabulary on training pairs first")
        self._validate(pairs)
        prev = self.vectorizer.transform(pairs["previous_text"])
        current = self.vectorizer.transform(pairs["current_text"])
        similarities = np.asarray(prev.multiply(current).sum(axis=1)).ravel()
        zero_vector = (np.asarray(prev.sum(axis=1)).ravel() == 0) | (np.asarray(current.sum(axis=1)).ravel() == 0)
        # Cosine is undefined for zero vectors. The model imputes from training only.
        similarities[zero_vector] = np.nan
        lengths, jaccards = [], []
        for old, new in zip(pairs["previous_text"], pairs["current_text"], strict=True):
            old_tokens, new_tokens = TOKEN.findall(old.lower()), TOKEN.findall(new.lower())
            lengths.append(np.log1p(len(new_tokens)) - np.log1p(len(old_tokens)))
            a, b = set(old_tokens), set(new_tokens)
            jaccards.append(1 - len(a & b) / len(a | b))
        result = pd.DataFrame({"log_length_change": lengths, "jaccard_distance": jaccards,
                               "tfidf_cosine_distance": np.clip(1 - similarities, 0, 1)}, index=pairs.index)
        result.attrs["zero_vocabulary_pairs"] = int(zero_vector.sum())
        return result
