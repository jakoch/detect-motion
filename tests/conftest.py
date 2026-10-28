"""Shared fixtures for detect-motion tests."""

import numpy as np
import pytest


@pytest.fixture
def quiet_scores():
    """Scores representing a quiet video with occasional noise spikes."""
    return np.array([0.0, 0.001, 0.0, 0.0005, 0.0, 0.0, 0.002, 0.0])


@pytest.fixture
def active_scores():
    """Scores representing a video with sustained movement."""
    return np.array([0.05, 0.08, 0.03, 0.06, 0.04, 0.07, 0.05, 0.09])


@pytest.fixture
def mixed_scores():
    """Scores with quiet baseline and several motion spikes."""
    return np.array([0.0, 0.0, 0.08, 0.0, 0.001, 0.09, 0.0, 0.0, 0.07, 0.0])
