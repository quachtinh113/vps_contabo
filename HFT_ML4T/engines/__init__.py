"""
HFT_ML4T Engines Package
"""

from .avellaneda_stoikov import (
    AvellanedaStoikovEngine,
    calculate_order_flow_imbalance,
    calculate_micro_volatility
)
from .ml4t_meta_labeler import (
    CUSUMEventFilter,
    calculate_garman_klass_volatility,
    calculate_triple_barriers,
    MLMetaGatekeeper,
    calculate_macro_regime_slope,
    calculate_macro_trend_ema200
)
from .position_sizer import PositionSizer
from .hrp_allocator import HierarchicalRiskParityAllocator
from .ml4t_data_pipeline import (
    ParquetFeatureCollector,
    TripleBarrierMetaLabeler,
    OrthogonalFactorNeutralizer,
    CombinatorialPurgedCrossValidation
)

__all__ = [
    "AvellanedaStoikovEngine",
    "calculate_order_flow_imbalance",
    "calculate_micro_volatility",
    "CUSUMEventFilter",
    "calculate_garman_klass_volatility",
    "calculate_triple_barriers",
    "MLMetaGatekeeper",
    "calculate_macro_regime_slope",
    "calculate_macro_trend_ema200",
    "PositionSizer",
    "HierarchicalRiskParityAllocator",
    "ParquetFeatureCollector",
    "TripleBarrierMetaLabeler",
    "OrthogonalFactorNeutralizer",
    "CombinatorialPurgedCrossValidation",
]
