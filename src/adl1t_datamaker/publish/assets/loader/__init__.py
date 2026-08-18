# The loading pipeline that ships with the record.
#
# Four stages run in order and each one caches what it wrote, so a rerun picks up where
# the last one stopped:
#
#   extraction      the published tables -> one file per object collection
#   processing      the saturation cuts, per event and per object
#   mlready         select the training features, normalise, pad to a common schema
#   awkward2torch   stack the collections into one (events, constituents, features) tensor
#
# The stages are configured by the hydra tree under configs/, which names them by their
# _target_. datamodule.L1ADData drives all four for a caller who wants tensors and
# nothing else.
#
# Nothing is imported here, so that the three stages before the last one can be used
# without torch installed.
