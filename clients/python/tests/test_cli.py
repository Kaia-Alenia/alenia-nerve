from unittest.mock import patch, MagicMock

import pytest

from nerve import __version__
from nerve.cli import main, BANNER, HELP_TEXT, PURPLE, RESET, YELLOW, RED


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
    with patch("sys.argv", ["nerve"] + args):
        with pytest.raises(SystemExit):
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
    with patch("sys.argv", ["nerve"] + args):
        with pytest.raises(SystemExit):
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

    with patch("sys.argv", ["nerve", "start"]):
        with pytest.raises(SystemExit):
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

    with patch("sys.argv", ["nerve", "start"]):
        with pytest.raises(SystemExit):
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

    with patch("sys.argv", ["nerve", "start"]):
        with pytest.raises(SystemExit):
            main()

    captured = capsys.readouterr()
    assert f"{RED}[NERVE CLI] Critical error: {error_msg}{RESET}\n" in captured.out
    mock_sys_exit.assert_called_once_with(1)


def test_unrecognized_command(mock_sys_exit, capsys):
    with patch("sys.argv", ["nerve", "foo"]):
        with pytest.raises(SystemExit):
            main()

    captured = capsys.readouterr()
    assert f"{RED}[NERVE CLI] Unrecognized command: 'foo'{RESET}\n" in captured.out
    assert BANNER in captured.out
    assert HELP_TEXT in captured.out
    mock_sys_exit.assert_called_once_with(1)
