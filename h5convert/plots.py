# Plotting of the features that are stored in the converted h5s.

import os
import operator
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


def plot_hist_3d(data: np.ndarray, object_type: str, feats: list, outdir: Path):
    """Plots data in 3d numpy array.

    The expected format of the data is nevents x nobjects x feats.
    Thus, this method plots a histogram of each feature of each object across all
    events in the given data numpy array.
    """
    outdir = outdir / f"{object_type}_plots"
    outdir.mkdir(parents=True, exist_ok=True)

    plt.rc("xtick", labelsize=23)
    plt.rc("ytick", labelsize=23)
    plt.rc("axes", titlesize=25)
    plt.rc("axes", labelsize=25)
    plt.rc("legend", fontsize=22)

    colors = ["#648FFF", "#785EF0", "#DC267F", "#FE6100", "#FFB000"]

    for feat_nb in range(data.shape[2]):
        plt.xlim(np.amin(data[:, :, feat_nb]), np.amax(data[:, :, feat_nb]))
        plt.figure(figsize=(12, 10))
        plt.hist(
            x=data[:, :, feat_nb].flatten(),
            bins=60,
            alpha=0.5,
            histtype="step",
            linewidth=2.5,
            density=True,
            color="midnightblue",
        )

        plt.xlabel(feats[feat_nb])
        plt.ylabel("Density")
        plt.gca().set_yscale("log")
        plt.savefig(outdir / f"{feats[feat_nb]}.png")
        plt.close()

    print(f"Plots for {object_type} saved to: ", outdir, "\U0001f4ca")


def plot_hist_2d(data: np.ndarray, object_type: str, feats: list, outdir: Path):
    """Plots data in 2d numpy array.

    The expected format of the data is nevents x feats.
    Thus, this method plots a histogram of each feature across all events.
    """
    outdir = outdir / f"{object_type}_plots"
    outdir.mkdir(parents=True, exist_ok=True)

    plt.rc("xtick", labelsize=23)
    plt.rc("ytick", labelsize=23)
    plt.rc("axes", titlesize=25)
    plt.rc("axes", labelsize=25)
    plt.rc("legend", fontsize=22)

    colors = ["#648FFF", "#785EF0", "#DC267F", "#FE6100", "#FFB000"]

    for feat_nb in range(data.shape[1]):
        plt.xlim(np.amin(data[:, feat_nb]), np.amax(data[:, feat_nb]))
        plt.figure(figsize=(12, 10))
        plt.hist(
            x=data[:, feat_nb].flatten(),
            bins=60,
            alpha=0.5,
            histtype="step",
            linewidth=2.5,
            density=True,
            color="midnightblue",
        )

        plt.xlabel(feats[feat_nb])
        plt.ylabel("Density")
        plt.gca().set_yscale("log")
        plt.savefig(outdir / f"{feats[feat_nb]}.png")
        plt.close()

    print(f"Plots for {object_type} saved to: ", outdir, "\U0001f4ca")


def plot_hist_1d(data: np.ndarray, feat: str, outdir: Path):
    """Plots data in 1d numpy array."""
    outdir = outdir / f"{feat}_plots"
    outdir.mkdir(parents=True, exist_ok=True)

    plt.rc("xtick", labelsize=23)
    plt.rc("ytick", labelsize=23)
    plt.rc("axes", titlesize=25)
    plt.rc("axes", labelsize=25)
    plt.rc("legend", fontsize=22)

    colors = ["#648FFF", "#785EF0", "#DC267F", "#FE6100", "#FFB000"]

    plt.xlim(np.amin(data), np.amax(data))
    plt.figure(figsize=(12, 10))
    plt.hist(
        x=data.flatten(),
        bins=60,
        alpha=0.5,
        histtype="step",
        linewidth=2.5,
        density=True,
        color="midnightblue",
    )
    plt.xlabel(feat)
    plt.ylabel("Density")
    plt.gca().set_yscale("log")
    plt.savefig(outdir / f"{feat}.png")
    plt.close()

    print(f"Plots for {feat} saved to: ", outdir, "\U0001f4ca")
