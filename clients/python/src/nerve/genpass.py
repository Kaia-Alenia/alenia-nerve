# -----------------------------------------------------------------------------
# This file is part of Nerve.
#
# Nerve is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# Nerve is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Nerve. If not, see <https://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------

import importlib.resources
import math
import secrets
import string


def generate_random_password(length: int = 20) -> tuple[str, float]:
    """
    Generates a strong random password and returns it along with its entropy.
    Uses ascii_letters + digits + punctuation (94 characters).
    Entropy = length * log2(94).
    """
    alphabet = string.ascii_letters + string.digits + string.punctuation
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    entropy = length * math.log2(len(alphabet))
    return password, entropy


def generate_passphrase(
    words: int = 5, separator: str = "-", append_digits: int = 0
) -> tuple[str, float]:
    """
    Generates a memorable passphrase using the EFF Large Wordlist and returns it along with its entropy.
    Entropy = words * log2(7776) + append_digits * log2(10).
    """
    # Load wordlist using importlib.resources
    # This ensures it works correctly when installed as a package
    text_content = (
        importlib.resources.files("nerve")
        .joinpath("eff_large_wordlist.txt")
        .read_text(encoding="utf-8")
    )
    wordlist = [
        line.strip()
        for line in text_content.splitlines()
        if line.strip() and not line.startswith("#")
    ]

    if not wordlist:
        raise ValueError("Wordlist is empty or could not be read.")

    selected_words = [secrets.choice(wordlist) for _ in range(words)]
    passphrase = separator.join(selected_words)

    entropy = words * math.log2(len(wordlist))

    if append_digits > 0:
        digits = "".join(secrets.choice(string.digits) for _ in range(append_digits))
        passphrase += digits
        entropy += append_digits * math.log2(10)

    return passphrase, entropy
