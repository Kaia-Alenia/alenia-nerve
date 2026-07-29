import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nerve import __version__
from nerve.cli import BANNER, HELP_TEXT, PURPLE, RED, RESET, YELLOW, main


@pytest.fixture
def mock_sys_exit():
    with patch("sys.exit", side_effect=SystemExit) as mock_exit:
        yield mock_exit


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--help"],
        ["-h"],
        ["help"],
    ],
)
def test_print_help_and_exit(args, mock_sys_exit, capsys):
    with patch("sys.argv", ["nerve"] + args), pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert BANNER in captured.out
    assert HELP_TEXT in captured.out
    mock_sys_exit.assert_called_once_with(0)


@pytest.mark.parametrize(
    "args",
    [
        ["--version"],
        ["-V"],
    ],
)
def test_print_version_and_exit(args, mock_sys_exit, capsys):
    with patch("sys.argv", ["nerve"] + args), pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert f"alenia-nerve {__version__}\n" == captured.out
    mock_sys_exit.assert_called_once_with(0)


@patch("nerve.cli.NexusHub")
def test_start_command(mock_nexus_hub, capsys):
    mock_hub_instance = MagicMock()
    mock_nexus_hub.return_value = mock_hub_instance

    with patch("sys.argv", ["nerve", "start"]):
        main()

    captured = capsys.readouterr()
    assert BANNER in captured.out
    assert f"{PURPLE}[NERVE CLI] Initializing Nerve Hub...{RESET}\n" in captured.out

    mock_nexus_hub.assert_called_once_with(verbose=False)
    mock_hub_instance.start.assert_called_once()


@pytest.mark.parametrize(
    "args",
    [
        ["start", "--verbose"],
        ["start", "-v"],
    ],
)
@patch("nerve.cli.NexusHub")
def test_start_command_verbose(mock_nexus_hub, args, capsys):
    mock_hub_instance = MagicMock()
    mock_nexus_hub.return_value = mock_hub_instance

    with patch("sys.argv", ["nerve"] + args):
        main()

    captured = capsys.readouterr()
    assert f"{YELLOW}[NERVE CLI] Verbose logging activated.{RESET}\n" in captured.out

    mock_nexus_hub.assert_called_once_with(verbose=True)


@patch("nerve.cli.NexusHub")
def test_start_keyboard_interrupt(mock_nexus_hub, mock_sys_exit, capsys):
    mock_hub_instance = MagicMock()
    mock_hub_instance.start.side_effect = KeyboardInterrupt()
    mock_nexus_hub.return_value = mock_hub_instance

    with patch("sys.argv", ["nerve", "start"]), pytest.raises(SystemExit):
        main()

    mock_hub_instance.stop.assert_called_once()
    captured = capsys.readouterr()
    assert f"\n{PURPLE}[NERVE CLI] Stopped by user.{RESET}\n" in captured.out
    mock_sys_exit.assert_called_once_with(0)


@patch("nerve.cli.NexusHub")
def test_start_os_error(mock_nexus_hub, mock_sys_exit, capsys):
    mock_hub_instance = MagicMock()
    error_msg = "Address already in use"
    mock_hub_instance.start.side_effect = OSError(error_msg)
    mock_nexus_hub.return_value = mock_hub_instance

    with patch("sys.argv", ["nerve", "start"]), pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert f"{RED}[NERVE CLI] Socket error: {error_msg}{RESET}\n" in captured.out
    mock_sys_exit.assert_called_once_with(1)


@patch("nerve.cli.NexusHub")
def test_start_critical_error(mock_nexus_hub, mock_sys_exit, capsys):
    mock_hub_instance = MagicMock()
    error_msg = "Something went horribly wrong"
    mock_hub_instance.start.side_effect = Exception(error_msg)
    mock_nexus_hub.return_value = mock_hub_instance

    with patch("sys.argv", ["nerve", "start"]), pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert f"{RED}[NERVE CLI] Critical error: {error_msg}{RESET}\n" in captured.out
    mock_sys_exit.assert_called_once_with(1)


def test_unrecognized_command(mock_sys_exit, capsys):
    with patch("sys.argv", ["nerve", "foo"]), pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert f"{RED}[NERVE CLI] Unrecognized command: 'foo'{RESET}\n" in captured.out
    assert BANNER in captured.out
    assert HELP_TEXT in captured.out
    mock_sys_exit.assert_called_once_with(1)


# -----------------------------------------------------------------------------
# End-to-End Subprocess Tests for CLI
# -----------------------------------------------------------------------------


def run_cli(*args, env=None):
    cmd = [sys.executable, "-m", "nerve.cli"] + list(args)
    test_env = os.environ.copy()
    if env:
        test_env.update(env)
    return subprocess.run(
        cmd, env=test_env, capture_output=True, text=True, check=False
    )


def test_cli_pack_no_args():
    result = run_cli("pack")
    assert result.returncode == 1
    assert "Usage: nerve pack <source> <output.nrv>" in result.stdout


def test_cli_unpack_no_args():
    result = run_cli("unpack")
    assert result.returncode == 1
    assert "Usage: nerve unpack <nrv_file> <out_dir>" in result.stdout


def test_cli_pack_unpack_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_file = tmp_path / "secret.txt"
        source_file.write_text("Hello, Nerve!")

        nrv_file = tmp_path / "secret.nrv"
        out_dir = tmp_path / "output"

        env = {"NERVE_NRV_PASSWORD": "testpassword123"}

        # Pack
        pack_res = run_cli("pack", str(source_file), str(nrv_file), env=env)
        assert pack_res.returncode == 0
        assert "Pack successful" in pack_res.stdout
        assert nrv_file.exists()

        # Unpack
        unpack_res = run_cli("unpack", str(nrv_file), str(out_dir), env=env)
        assert unpack_res.returncode == 0
        assert "Unpack successful" in unpack_res.stdout

        # Verify
        unpacked_file = out_dir / "secret.txt"
        assert unpacked_file.exists()
        assert unpacked_file.read_text() == "Hello, Nerve!"


def test_cli_unpack_wrong_password():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_file = tmp_path / "secret.txt"
        source_file.write_text("Hello, Nerve!")

        nrv_file = tmp_path / "secret.nrv"
        out_dir = tmp_path / "output"

        # Pack
        run_cli(
            "pack",
            str(source_file),
            str(nrv_file),
            env={"NERVE_NRV_PASSWORD": "correct_pass"},
        )

        # Unpack with wrong pass
        unpack_res = run_cli(
            "unpack",
            str(nrv_file),
            str(out_dir),
            env={"NERVE_NRV_PASSWORD": "wrong_pass"},
        )
        assert unpack_res.returncode == 1
        assert "Error" in unpack_res.stdout
        assert "Traceback" not in unpack_res.stderr
        assert "Traceback" not in unpack_res.stdout
