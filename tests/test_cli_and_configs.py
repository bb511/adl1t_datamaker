"""Every script starts and every experiment config composes. Fast, no data."""

import subprocess
import sys
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "scripts" / "configs"

# convert_run and summary_run are left out: they take hydra key=value overrides rather
# than flags, so there is no flag list to check them against. The config composition
# tests below cover them instead.
ARGPARSE_SCRIPTS = ["convert", "convert_folder", "summary", "summary_comparison"]
BASE_CONFIGS = ["convert.yaml", "summary.yaml"]
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


def composed(experiment: str, base: str = "convert.yaml"):
    """One experiment composed against a base config, as the scripts do it.

    output_root_path is a mandatory ``???`` in both bases, and reading it unset raises
    MissingMandatoryValue, so the override below stands in for the real output root.

    :param base: One of BASE_CONFIGS, the two entry points that take an experiment.
    """
    with initialize_config_dir(config_dir=str(CONFIG_DIR), version_base=None):
        return compose(
            config_name=base,
            overrides=[f"+experiment={experiment}", "output_root_path=/tmp/adl1t-test"],
        )


@pytest.mark.parametrize("base", BASE_CONFIGS)
@pytest.mark.parametrize("experiment", EXPERIMENTS)
def test_experiment_config_composes(experiment, base):
    """Both entry points share the experiment configs, so both must compose them.

    summary.yaml has to keep the converter group for the same reason convert.yaml does:
    the 2025E and 2025G experiments override it to 'unpacked'.
    """
    cfg = composed(experiment, base)

    assert isinstance(cfg.converter.mc, bool), "mc must be resolved by the experiment"
    assert cfg.paths.input_root_path
    assert cfg.paths.input_output_folders
    assert cfg.paths.auxiliary_files.prescale_file


@pytest.mark.parametrize("experiment", EXPERIMENTS)
def test_experiment_prescale_menu_exists(experiment):
    """A config naming a menu that is not checked in would fail only at conversion."""
    cfg = composed(experiment)

    menu = REPO_ROOT / cfg.paths.auxiliary_files.prescale_file
    assert menu.is_file(), f"{experiment} names a missing menu: {menu}"


def load_script(name: str):
    """Import a script under scripts/ as a module, to test its helpers directly.

    The scripts carry a shebang and no .py suffix, so the import machinery has to be
    pointed at the file rather than left to find it.
    """
    import importlib.util
    from importlib.machinery import SourceFileLoader

    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def test_summary_run_walks_output_folders_in_a_stable_order():
    """The old plot_run took a set(), so the campaign table order varied between runs."""
    cfg = composed("L1TNtupleRun3-142XWinter25", "summary.yaml")
    folders = load_script("summary_run").output_folders(cfg)

    assert folders == sorted(folders), "campaign order must not depend on set iteration"
    assert len(folders) == len(set(folders)), "one output folder must be visited once"


def test_summary_run_records_every_input_that_fed_one_output_folder():
    """Only the config knows which inputs fed one output folder.

    Several input directories map onto one, and nobody could reconstruct that from the
    parquet afterwards.
    """
    cfg = composed("L1TNtupleRun3-142XWinter25", "summary.yaml")
    module = load_script("summary_run")
    merged = next(
        folder for folder in module.output_folders(cfg)
        if folder.name.startswith("HHHto4B2Tau")
    )
    recorded = module.provenance(cfg, merged)

    assert len(recorded["inputs"]) == 4, "the four shard directories were not recorded"
    assert recorded["inputs"] == sorted(recorded["inputs"])
    assert recorded["mc"] is True
    assert recorded["prescale_file"].endswith(".csv")
    assert "silent" not in recorded, "a converter flag is not provenance"


@pytest.mark.parametrize("experiment", [e for e in EXPERIMENTS if e.startswith("EphZB")])
def test_real_data_runs_have_pileup_files(experiment):
    """Real data needs a brilcalc file per run or the conversion raises ValueError."""
    cfg = composed(experiment)

    assert cfg.converter.mc is False
    runs = [part for part in experiment.replace("-", "_").split("_") if part.isdigit()]
    folder = REPO_ROOT / cfg.paths.auxiliary_files.pileup_folder
    for run in (run for run in runs if len(run) == 6):
        assert any(folder.glob(f"run{run}*")), f"{experiment}: no brilcalc file for {run}"
