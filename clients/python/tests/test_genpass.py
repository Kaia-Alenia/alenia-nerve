import pytest
import importlib.resources
from nerve.genpass import generate_random_password, generate_passphrase

def test_random_password_length_and_alphabet():
    length = 30
    password, entropy = generate_random_password(length=length)
    assert len(password) == length
    # Alphabet contains 94 chars, entropy = length * log2(94)
    expected_entropy = length * 6.554588851677638
    assert abs(entropy - expected_entropy) < 0.01

def test_passphrase_words_and_separator():
    words = 7
    separator = "_"
    passphrase, entropy = generate_passphrase(words=words, separator=separator)
    parts = passphrase.split(separator)
    assert len(parts) == words
    # Entropy = words * log2(7776)
    expected_entropy = words * 12.92481250360578
    assert abs(entropy - expected_entropy) < 0.01

def test_passphrase_with_digits():
    words = 4
    append_digits = 2
    passphrase, entropy = generate_passphrase(words=words, append_digits=append_digits)
    # The last 2 chars should be digits
    assert passphrase[-2:].isdigit()
    # Expected entropy = 4 * log2(7776) + 2 * log2(10)
    expected_entropy = (4 * 12.92481250360578) + (2 * 3.321928094887362)
    assert abs(entropy - expected_entropy) < 0.01

def test_resource_localization():
    """Verify that eff_large_wordlist.txt can be found and read via importlib.resources."""
    try:
        content = importlib.resources.files('nerve').joinpath('eff_large_wordlist.txt').read_text(encoding='utf-8')
        assert len(content) > 0
        # Should have 7776 words plus headers
        lines = content.splitlines()
        words = [line for line in lines if line.strip() and not line.startswith('#')]
        assert len(words) == 7776
    except Exception as e:
        pytest.fail(f"Could not load eff_large_wordlist.txt via importlib.resources: {e}")

def test_non_repetition():
    """Generate 10000 times and ensure no two consecutive generations are identical."""
    prev_random = ""
    prev_passphrase = ""
    for _ in range(10000):
        # We test with small length/words to increase collision probability artificially,
        # but with secrets it should still essentially never happen for any reasonable length
        r_pwd, _ = generate_random_password(length=8)
        p_pwd, _ = generate_passphrase(words=3)
        
        assert r_pwd != prev_random, "Detected identical consecutive random passwords"
        assert p_pwd != prev_passphrase, "Detected identical consecutive passphrases"
        
        prev_random = r_pwd
        prev_passphrase = p_pwd
