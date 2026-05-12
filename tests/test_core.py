def test_import_nerve():
    try:
        from nerve import NexusHub, NexusClient
        assert True
    except ImportError:
        assert False, "Could not import nerve"
