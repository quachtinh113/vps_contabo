"""
HFT_ML4T — Hierarchical Risk Parity (HRP) Portfolio Allocator
Implementation of Marcos López de Prado (2016) "Building Diversified Portfolios that Outperform Out-of-Sample".

Overcomes traditional Markowitz Mean-Variance instability by using:
  1. Tree Clustering (Hierarchical Linkage on Correlation Distance)
  2. Quasi-Diagonalization (Reordering Covariance Matrix)
  3. Recursive Bisection (Top-down Risk Budgeting without Matrix Inversion)
"""

import math
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, to_tree


class HierarchicalRiskParityAllocator:
    """
    Hierarchical Risk Parity (HRP) allocation engine for multi-asset HFT portfolios.
    Optimizes capital weights across Crypto, Metals, Energy, Indices, and FX pairs.
    """

    def __init__(self, linkage_method: str = "single"):
        """
        :param linkage_method: Hierarchical clustering linkage method ('single', 'complete', 'average', 'ward')
        """
        self.linkage_method = linkage_method

    @staticmethod
    def correlation_to_distance(corr: np.ndarray) -> np.ndarray:
        """
        Transforms correlation matrix rho into a valid metric distance space:
          d_i,j = sqrt( 0.5 * (1 - rho_i,j) )
        Guarantees d_i,j in [0, 1] with d_i,i = 0 and satisfies triangle inequality.
        """
        dist = np.sqrt(np.maximum(0.0, 0.5 * (1.0 - corr)))
        np.fill_diagonal(dist, 0.0)
        return dist

    @staticmethod
    def quasi_diagonalize(link: np.ndarray, num_items: int) -> List[int]:
        """
        Reorders items based on the hierarchical linkage dendrogram so that
        highly correlated assets are placed adjacent to each other.
        """
        root = to_tree(link)
        
        def _get_leaf_order(node):
            if node.is_leaf():
                return [node.id]
            return _get_leaf_order(node.left) + _get_leaf_order(node.right)

        return _get_leaf_order(root)

    @staticmethod
    def get_cluster_variance(cov: np.ndarray, cluster_indices: List[int]) -> float:
        """
        Computes cluster variance using intra-cluster inverse-variance weighting:
          w_k = diag(cov_k)^(-1) / sum(diag(cov_k)^(-1))
          V_k = w_k.T @ cov_k @ w_k
        """
        sub_cov = cov[np.ix_(cluster_indices, cluster_indices)]
        inv_diag = 1.0 / np.maximum(1e-8, np.diag(sub_cov))
        weights = inv_diag / np.sum(inv_diag)
        var = float(np.dot(weights, np.dot(sub_cov, weights)))
        return max(1e-8, var)

    def allocate(
        self,
        returns_df: pd.DataFrame,
        min_weight_cap: float = 0.05,
        max_weight_cap: float = 0.40
    ) -> Dict[str, float]:
        """
        Computes optimal HRP portfolio weights from an asset returns DataFrame.
        
        :param returns_df: DataFrame where each column is an asset's price return series
        :param min_weight_cap: Minimum allocation floor per asset
        :param max_weight_cap: Maximum allocation ceiling per asset
        :return: Dict[str, float] of normalized asset weights summing to 1.0
        """
        if returns_df is None or returns_df.empty or returns_df.shape[1] < 2:
            cols = returns_df.columns if returns_df is not None else []
            if len(cols) == 1:
                return {cols[0]: 1.0}
            return {}

        assets = list(returns_df.columns)
        n = len(assets)

        cov = returns_df.cov().values
        corr = returns_df.corr().values

        # Handle zero variance or NaN
        if np.isnan(corr).any() or np.isnan(cov).any():
            return {a: round(1.0 / n, 4) for a in assets}

        # 1. Tree Clustering
        dist = self.correlation_to_distance(corr)
        
        # Condensed distance array for scipy linkage
        from scipy.spatial.distance import squareform
        condensed_dist = squareform(dist, checks=False)
        link = linkage(condensed_dist, method=self.linkage_method)

        # 2. Quasi-Diagonalization
        sorted_indices = self.quasi_diagonalize(link, n)

        # 3. Recursive Bisection
        weights = pd.Series(1.0, index=sorted_indices)
        clusters = [sorted_indices]

        while len(clusters) > 0:
            next_clusters = []
            for cluster in clusters:
                if len(cluster) > 1:
                    mid = len(cluster) // 2
                    c1 = cluster[:mid]
                    c2 = cluster[mid:]

                    var1 = self.get_cluster_variance(cov, c1)
                    var2 = self.get_cluster_variance(cov, c2)

                    # Allocation factor based on cluster variances
                    alpha1 = 1.0 - (var1 / (var1 + var2))
                    alpha2 = 1.0 - alpha1

                    weights.loc[c1] *= alpha1
                    weights.loc[c2] *= alpha2

                    next_clusters.append(c1)
                    next_clusters.append(c2)
            clusters = next_clusters

        # Map back to asset names
        raw_weights = {assets[idx]: float(weights.loc[idx]) for idx in sorted_indices}

        # 4. Apply min/max weight caps & renormalize
        capped_weights = {}
        for a, w in raw_weights.items():
            capped_weights[a] = max(min_weight_cap, min(max_weight_cap, w))

        total_w = sum(capped_weights.values())
        final_weights = {a: round(w / total_w, 4) for a, w in capped_weights.items()}

        return final_weights
