# Turning a converted data set into a published release.
#
# Kept apart from the rest of the package because it works the other way round: the
# modules above convert ntuples into parquet and measure what came out, while these
# take finished parquet and package it for a repository. They read the producer (the
# feature specification through schema.py, the row counts through summary.py) but
# nothing in the producer reads them.
#
# export      partition a data set by a frozen split map, then archive it
# card        the dataset card and licence that ship inside the record
# huggingface the row-per-event mirror
# assets      the loading pipeline and its configs, which ship inside the mirror
