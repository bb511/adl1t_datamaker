"""Every script starts and every experiment config composes. Fast, no data."""

import subprocess
import sys
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "scripts" / "configs"

# The hydra scripts take key=value overrides rather than flags, so --help does not
# apply to them; they are covered by the config composition tests instead.
ARGPARSE_SCRIPTS = ["convert", "convert_folder", "plot", "plot_comparison"]
EXPERIMENTS = sorted(path.stem for path in (CONFIG_DIR / "experiment").glob("*.yaml"))


def script_help(script: str) -> subprocess.CompletedProcess:
    """Run a script's --help from the repo root, which is where the docs say to run."""
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("script", ARGPARSE_SCRIPTS)
def test_help_exits_cleanly(script):
    result = script_help(script)
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()


def test_calosumm_flag_is_spelled_correctly():
    """run.snip used to pass --caolsumm_tree_name, which argparse rejects."""
    assert "--calosumm_tree_name" in script_help("convert").stdout


def test_run_snip_examples_use_real_flags():
    """Every long flag in the usage examples must exist in the matching script."""
    helptexts = {name: script_help(name).stdout for name in ARGPARSE_SCRIPTS}

    for line in (REPO_ROOT / "scripts" / "run.snip").read_text().splitlines():
        if not line.startswith("./scripts/"):
            continue
        script = line.split()[0].removeprefix("./scripts/")
        if script not in helptexts:
            continue
        for token in line.split():
            if token.startswith("--"):
                assert token in helptexts[script], f"{script} has no {token} (run.snip)"


def test_run_snip_invokes_from_the_repo_root():
    """The examples pass repo-root-relative paths, so they must call scripts/<name>."""
    for line in (REPO_ROOT / "scripts" / "run.snip").read_text().splitlines():
        if line.startswith("./") or line.startswith("scripts/"):
            assert line.startswith("./scripts/"), f"not runnable from repo root: {line}"


@pytest.mark.parametrize("experiment", EXPERIMENTS)
def test_experiment_config_composes(experiment):
    with initialize_config_dir(config_dir=str(CONFIG_DIR), version_base=None):
        cfg = compose(
            config_name="convert.yaml",
            overrides=[f"+experiment={experiment}", "output_root_path=/tmp/adl1t-test"],
        )

    assert isinstance(cfg.converter.mc, bool), "mc must be resolved by the experiment"
    assert cfg.paths.input_root_path
    assert cfg.paths.input_output_folders
    assert cfg.paths.auxiliary_files.prescale_file


@pytest.mark.parametrize("experiment", EXPERIMENTS)
def test_experiment_prescale_menu_exists(experiment):
    """A config naming a menu that is not checked in would fail only at conversion."""
    with initialize_config_dir(config_dir=str(CONFIG_DIR), version_base=None):
        cfg = compose(
            config_name="convert.yaml",
            overrides=[f"+experiment={experiment}", "output_root_path=/tmp/adl1t-test"],
        )

    menu = REPO_ROOT / cfg.paths.auxiliary_files.prescale_file
    assert menu.is_file(), f"{experiment} names a missing menu: {menu}"


@pytest.mark.parametrize("experiment", [e for e in EXPERIMENTS if e.startswith("EphZB")])
def test_real_data_runs_have_pileup_files(experiment):
    """Real data needs a brilcalc file per run or the conversion raises ValueError."""
    with initialize_config_dir(config_dir=str(CONFIG_DIR), version_base=None):
        cfg = compose(
            config_name="convert.yaml",
            overrides=[f"+experiment={experiment}", "output_root_path=/tmp/adl1t-test"],
        )

    assert cfg.converter.mc is False
    runs = [part for part in experiment.replace("-", "_").split("_") if part.isdigit()]
    folder = REPO_ROOT / cfg.paths.auxiliary_files.pileup_folder
    for run in (run for run in runs if len(run) == 6):
        assert any(folder.glob(f"run{run}*")), f"{experiment}: no brilcalc file for {run}"
