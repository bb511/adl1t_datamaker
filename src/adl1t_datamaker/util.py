# Utility methods for the h5 converter.
from contextlib import redirect_stdout
from io import StringIO
import pathlib
from pathlib import Path
import XRootD.client.glob_funcs as xglob

import rich
import rich.syntax
import rich.tree
from omegaconf import DictConfig, OmegaConf


class NullIO(StringIO):
    def write(self, txt: str) -> None:
        pass


def silent(fn):
    """Decorator to silence functions."""
    def silent_fn(*args, **kwargs):
        with redirect_stdout(NullIO()):
            return fn(*args, **kwargs)

    return silent_fn


def check_xrootd_path(path: str) -> Path | str:
    if 'root://' in path:
        return path

    return Path(path)


def glob(folder: Path | str, string: str) -> list[str]:
    if isinstance(folder, pathlib.PurePath):
        return list(self.input_folder.glob(string))
    else:
        return list(xglob.glob(folder + "/" + string))


def print_config(cfg: DictConfig, resolve: bool = False, save: bool = False) -> None:
    """Prints the contents of a DictConfig as a tree structure using the Rich library.

    :param cfg: A DictConfig composed by Hydra.
    :param resolve: Whether to resolve reference fields of DictConfig.
        Default is ``False``.
    :param save: Whether to export config to the hydra output folder.
        Default is ``False``.
    """
    style = "dim"
    tree = rich.tree.Tree("CONFIG", style=style, guide_style=style)

    queue = []

    # Add all fields in config to queue.
    for field in cfg:
        if field not in queue:
            queue.append(field)

    # Generate config tree from queue.
    for field in queue:
        branch = tree.add(field, style=style, guide_style=style)

        config_group = cfg[field]
        if isinstance(config_group, DictConfig):
            branch_content = OmegaConf.to_yaml(config_group, resolve=resolve)
        else:
            branch_content = str(config_group)

        branch.add(rich.syntax.Syntax(branch_content, "yaml"))

    # Print config tree.
    rich.print(tree)

    # Save config tree to file.
    if save:
        with open(Path(cfg.paths.output_dir, "config_tree.log"), "w") as file:
            rich.print(tree, file=file)
