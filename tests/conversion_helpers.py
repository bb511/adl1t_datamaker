"""The two tree-name sets a converter can be built with, shared across the suite."""

# scripts/configs/converter/default.yaml: emulated trees, so CICADA is available.
EMULATED = {
    "l1_tree_name": "l1UpgradeEmuTree/L1UpgradeTree",
    "uGT_tree_name": "l1uGTEmuTree/L1uGTTree",
    "event_tree_name": "l1EventTree/L1EventTree",
    "calosumm_tree_name": "l1CaloSummaryEmuTree/L1CaloSummaryTree",
}
# scripts/configs/converter/unpacked.yaml: raw trees, no calo summary and so no CICADA.
UNPACKED = {
    "l1_tree_name": "l1UpgradeTree/L1UpgradeTree",
    "uGT_tree_name": "l1uGTTree/L1uGTTree",
    "event_tree_name": "l1EventTree/L1EventTree",
    "calosumm_tree_name": None,
}
