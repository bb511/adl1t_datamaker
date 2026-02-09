# Plotting of the features that are stored in the converted h5s.

from pathlib import Path

import numpy as np
import awkward as ak
import matplotlib
import matplotlib.pyplot as plt
import mplhep as hep

# Plot configuration.
matplotlib.rcParams.update(matplotlib.rcParamsDefault)
hep.style.use("CMS")


def plot_hist(data: ak.Array, feat_name: str, outdir: Path):
    """Plots data in flat awkward array into a histogram."""
    # Flatten the data.
    data = ak.flatten(data, axis=None)
    # Clip unreasonable large values.
    data = ak.where(data > 1e15, 1e15, data)

    fig, ax = plt.subplots()
    histogram = np.histogram(data, bins='doane')
    hep.histplot(*histogram, density=True, ax=ax)
    hep.cms.label("Preliminary", data=False, com=14)

    if check_feature_is_Et(feat_name):
        ax.set_yscale('log')
    else:
        ax.ticklabel_format(
            axis="y", style="sci", scilimits=(-2, 2), useMathText=True, useOffset=False
        )

    ax.set_xlabel(feat_name)
    ax.ticklabel_format(
        axis='x', style="sci", scilimits=(-2, 2), useMathText=True, useOffset=False
    )

    ax.get_xaxis().get_offset_text().set_position((1.10, 1))
    ax.get_yaxis().get_offset_text().set_position((-0.12, 1))

    fig.savefig(outdir / f"{feat_name}.png")
    fig.clear()
    plt.close(fig)


def plot_comp_hist(
    data1: ak.Array,
    data2: ak.Array,
    feat_name: str,
    outdir: Path,
    label1 = 'data1',
    label2 = 'data2',
):
    """Plots comparison histogram between two flat awkward data arrays."""
    # Flatten the data.
    data1 = ak.flatten(data1, axis=None)
    data2 = ak.flatten(data2, axis=None)
    # Clip unreasonable large values.
    data1 = ak.where(data1 > 1e15, 1e15, data1)
    data2 = ak.where(data2 > 1e15, 1e15, data2)

    bins = np.histogram_bin_edges(np.concatenate([data1, data2]), bins='doane')
    counts1, _ = np.histogram(data1, bins=bins)
    counts2, _ = np.histogram(data2, bins=bins)

    # Make the main plot.
    fig, ax = plt.subplots()
    hep.histplot(
        counts1, bins=bins, label=label1, histtype='fill', ax=ax, color='C0', alpha=0.5
    )
    hep.histplot(
        counts2, bins=bins, label=label2, histtype='fill', ax=ax, color='C1', alpha=0.5
    )
    ax.legend()

    # Make the axes nice and readable.
    if check_feature_is_Et(feat_name):
        ax.set_yscale('log')
    else:
        ax.ticklabel_format(
            axis="y", style="sci", scilimits=(-2, 2), useMathText=True, useOffset=False
        )

    ax.set_xlabel(feat_name)
    ax.ticklabel_format(
        axis="x", style="sci", scilimits=(-2, 2), useMathText=True, useOffset=False
    )

    ax.get_xaxis().get_offset_text().set_position((1.10, 1))
    ax.get_yaxis().get_offset_text().set_position((-0.12, 1))

    fig.savefig(outdir / f"{feat_name}.png")
    fig.clear()
    plt.close(fig)

def check_feature_is_Et(feat_name: str):
    is_et = 'Et' in feat_name or 'EtUnconstrained' in feat_name or 'ETTEM' in feat_name
    is_not_eta = not 'Eta' in feat_name

    return (is_et and is_not_eta)
