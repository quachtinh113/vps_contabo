#!/usr/bin/env python3
"""Covariance Matrix Denoising & Detoning (Marcenko-Pastur Theorem).

Based on Marcos López de Prado, 'Machine Learning for Asset Managers' (Chapter 2).
In financial portfolios, empirical correlation matrices contain significant random noise.
1. Denoising: Uses Random Matrix Theory (Marcenko-Pastur distribution) to identify eigenvalues
   associated with pure noise and replaces them with their average.
2. Detoning: Removes the market component (largest eigenvalue) to isolate idiosyncratic alpha.
"""

from __future__ import annotations

import argparse
from typing import Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def fit_marcenko_pastur(var: float, q: float, pts: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
    """Calculate theoretical Marcenko-Pastur probability density function."""
    e_min = var * (1.0 - np.sqrt(q)) ** 2
    e_max = var * (1.0 + np.sqrt(q)) ** 2
    e_val = np.linspace(e_min, e_max, pts)
    pdf = q / (2.0 * np.pi * var * e_val) * np.sqrt((e_max - e_val) * (e_val - e_min))
    return e_val, pdf


def denoise_covariance(corr: np.ndarray, t: int, n: int, alpha: float = 0.0) -> np.ndarray:
    """Denoise empirical correlation matrix by constant residual shrinkage.

    Parameters
    ----------
    corr : np.ndarray
        N x N empirical correlation matrix.
    t : int
        Number of time-series observations (rows).
    n : int
        Number of assets (columns).
    alpha : float
        Shrinkage weight (0.0 = set noise eigenvalues to constant mean).

    Returns
    -------
    np.ndarray
        Denoised correlation matrix.
    """
    q = float(t) / float(n)
    e_val, e_vec = np.linalg.eigh(corr)
    # Sort eigenvalues in descending order
    indices = np.argsort(e_val)[::-1]
    e_val = e_val[indices]
    e_vec = e_vec[:, indices]

    # Theoretical upper bound for noise eigenvalues
    # Estimate variance of noise by fitting
    e_max = (1.0 + np.sqrt(1.0 / q)) ** 2

    # Identify noise indices
    n_facts = int(np.sum(e_val > e_max))
    n_facts = max(1, n_facts)

    # Constant residual eigenvalue method
    e_val_denoised = e_val.copy()
    noise_mean = np.mean(e_val[n_facts:])
    e_val_denoised[n_facts:] = noise_mean

    # Reconstruct correlation matrix
    corr_denoised = np.dot(e_vec, np.dot(np.diag(e_val_denoised), e_vec.T))

    # Rescale diagonal to 1.0
    diag = np.diag(corr_denoised)
    corr_denoised /= np.sqrt(np.outer(diag, diag))
    return corr_denoised


def detone_matrix(corr_denoised: np.ndarray, num_market_modes: int = 1) -> np.ndarray:
    """Remove market mode (first eigenvalues) to isolate pure idiosyncratic alpha correlations."""
    e_val, e_vec = np.linalg.eigh(corr_denoised)
    indices = np.argsort(e_val)[::-1]
    e_val = e_val[indices]
    e_vec = e_vec[:, indices]

    # Zero out the top market modes
    e_val_detoned = e_val.copy()
    e_val_detoned[:num_market_modes] = 0.0

    corr_detoned = np.dot(e_vec, np.dot(np.diag(e_val_detoned), e_vec.T))
    diag = np.diag(corr_detoned)
    # Prevent division by zero if completely detoned
    scale = np.sqrt(np.outer(diag, diag))
    scale[scale == 0] = 1.0
    corr_detoned /= scale
    np.fill_diagonal(corr_detoned, 1.0)
    return corr_detoned


def main() -> None:
    parser = argparse.ArgumentParser(description="Covariance Denoising & Detoning Engine")
    parser.add_argument("--test", action="store_true", help="Run automated test on synthetic correlation matrix")
    args = parser.parse_args()

    if args.test:
        np.random.seed(42)
        t, n = 500, 10
        raw_returns = np.random.normal(0, 1, (t, n))
        # Add common market factor
        market = np.random.normal(0, 1, (t, 1))
        returns = raw_returns + 0.8 * market

        corr = np.corrcoef(returns, rowvar=False)
        print(f"[*] Raw empirical correlation condition number: {np.linalg.cond(corr):.2f}")

        corr_clean = denoise_covariance(corr, t=t, n=n)
        print(f"[+] Denoised correlation condition number: {np.linalg.cond(corr_clean):.2f}")

        corr_detoned = detone_matrix(corr_clean, num_market_modes=1)
        print(f"[+] Detoned (market-neutral) correlation condition number: {np.linalg.cond(corr_detoned):.2f}")
        print("\nMean absolute off-diagonal correlation:")
        mask = ~np.eye(n, dtype=bool)
        print(f"  Raw:     {np.mean(np.abs(corr[mask])):.3f}")
        print(f"  Detoned: {np.mean(np.abs(corr_detoned[mask])):.3f} (True idiosyncratic alpha)")


if __name__ == "__main__":
    main()
