import pytest
from unittest.mock import patch, MagicMock
from nerve.cli_monitor import format_bytes, data_fetcher_loop, LATEST_DATA


@pytest.mark.parametrize(
    "b, expected",
    [
        (0, "0 B"),
        (500, "500 B"),
        (-500, "-500 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (int(1024 * 1024 * 2.5), "2.5 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
        (int(1024 * 1024 * 1024 * 3.7), "3.7 GB"),
        (1024 * 1024 * 1024 * 1024, "1.0 TB"),
        (1024 * 1024 * 1024 * 1024 * 5, "5.0 TB"),
        (1024 * 1024 * 1024 * 1024 * 1024, "1024.0 TB"),
    ],
)
def test_format_bytes(b, expected):
    assert format_bytes(b) == expected


def test_data_fetcher_loop_success():
    # Note: the issue description shows current_dashboard_data,
    # but the actual implementation uses LATEST_DATA and get_metrics().
    # We prioritize writing tests that pass against the real, existing codebase.
    client_mock = MagicMock()

    mock_metrics = {"uptime": 100.0}
    mock_clients = ["client1", "client2"]

    client_mock.get_metrics.return_value = mock_metrics
    client_mock.list_clients.return_value = mock_clients

    with patch("nerve.cli_monitor.time.sleep", side_effect=StopIteration):
        try:
            data_fetcher_loop(client_mock)
        except StopIteration:
            pass

    assert LATEST_DATA["metrics"] == mock_metrics
    assert LATEST_DATA["clients"] == mock_clients


def test_data_fetcher_loop_exception():
    client_mock = MagicMock()

    client_mock.get_metrics.side_effect = Exception("Failed to get metrics")

    with patch("nerve.cli_monitor.time.sleep", side_effect=StopIteration) as sleep_mock:
        try:
            data_fetcher_loop(client_mock)
        except StopIteration:
            pass

    sleep_mock.assert_called_once_with(1.0)
