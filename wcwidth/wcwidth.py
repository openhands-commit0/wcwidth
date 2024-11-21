"""
This is a python implementation of wcwidth() and wcswidth().

https://github.com/jquast/wcwidth

from Markus Kuhn's C code, retrieved from:

    http://www.cl.cam.ac.uk/~mgk25/ucs/wcwidth.c

This is an implementation of wcwidth() and wcswidth() (defined in
IEEE Std 1002.1-2001) for Unicode.

http://www.opengroup.org/onlinepubs/007904975/functions/wcwidth.html
http://www.opengroup.org/onlinepubs/007904975/functions/wcswidth.html

In fixed-width output devices, Latin characters all occupy a single
"cell" position of equal width, whereas ideographic CJK characters
occupy two such cells. Interoperability between terminal-line
applications and (teletype-style) character terminals using the
UTF-8 encoding requires agreement on which character should advance
the cursor by how many cell positions. No established formal
standards exist at present on which Unicode character shall occupy
how many cell positions on character terminals. These routines are
a first attempt of defining such behavior based on simple rules
applied to data provided by the Unicode Consortium.

For some graphical characters, the Unicode standard explicitly
defines a character-cell width via the definition of the East Asian
FullWidth (F), Wide (W), Half-width (H), and Narrow (Na) classes.
In all these cases, there is no ambiguity about which width a
terminal shall use. For characters in the East Asian Ambiguous (A)
class, the width choice depends purely on a preference of backward
compatibility with either historic CJK or Western practice.
Choosing single-width for these characters is easy to justify as
the appropriate long-term solution, as the CJK practice of
displaying these characters as double-width comes from historic
implementation simplicity (8-bit encoded characters were displayed
single-width and 16-bit ones double-width, even for Greek,
Cyrillic, etc.) and not any typographic considerations.

Much less clear is the choice of width for the Not East Asian
(Neutral) class. Existing practice does not dictate a width for any
of these characters. It would nevertheless make sense
typographically to allocate two character cells to characters such
as for instance EM SPACE or VOLUME INTEGRAL, which cannot be
represented adequately with a single-width glyph. The following
routines at present merely assign a single-cell width to all
neutral characters, in the interest of simplicity. This is not
entirely satisfactory and should be reconsidered before
establishing a formal standard in this area. At the moment, the
decision which Not East Asian (Neutral) characters should be
represented by double-width glyphs cannot yet be answered by
applying a simple rule from the Unicode database content. Setting
up a proper standard for the behavior of UTF-8 character terminals
will require a careful analysis not only of each Unicode character,
but also of each presentation form, something the author of these
routines has avoided to do so far.

http://www.unicode.org/unicode/reports/tr11/

Latest version: http://www.cl.cam.ac.uk/~mgk25/ucs/wcwidth.c
"""
from __future__ import division
import os
import sys
import warnings
from .table_vs16 import VS16_NARROW_TO_WIDE
from .table_wide import WIDE_EASTASIAN
from .table_zero import ZERO_WIDTH
from .unicode_versions import list_versions
try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache
_PY3 = sys.version_info[0] >= 3

def _bisearch(ucs, table):
    """
    Auxiliary function for binary search in interval table.

    :arg int ucs: Ordinal value of unicode character.
    :arg list table: List of starting and ending ranges of ordinal values,
        in form of ``[(start, end), ...]``.
    :rtype: int
    :returns: 1 if ordinal value ucs is found within lookup table, else 0.
    """
    min = 0
    max = len(table) - 1
    if ucs < table[0][0] or ucs > table[max][1]:
        return 0

    while max >= min:
        mid = (min + max) // 2
        if ucs > table[mid][1]:
            min = mid + 1
        elif ucs < table[mid][0]:
            max = mid - 1
        else:
            return 1

    return 0

@lru_cache(maxsize=1000)
def wcwidth(wc, unicode_version='auto'):
    """
    Given one Unicode character, return its printable length on a terminal.

    :param str wc: A single Unicode character.
    :param str unicode_version: A Unicode version number, such as
        ``'6.0.0'``. A list of version levels suported by wcwidth
        is returned by :func:`list_versions`.

        Any version string may be specified without error -- the nearest
        matching version is selected.  When ``latest`` (default), the
        highest Unicode version level is used.
    :return: The width, in cells, necessary to display the character of
        Unicode string character, ``wc``.  Returns 0 if the ``wc`` argument has
        no printable effect on a terminal (such as NUL '\\0'), -1 if ``wc`` is
        not printable, or has an indeterminate effect on the terminal, such as
        a control character.  Otherwise, the number of column positions the
        character occupies on a graphic terminal (1 or 2) is returned.
    :rtype: int

    See :ref:`Specification` for details of cell measurement.
    """
    ucs = ord(wc) if len(wc) else 0

    # Handle special cases first
    if ucs == 0:
        return 0

    if ucs < 32 or (0x7f <= ucs < 0xa0):
        return -1

    # Handle zero-width characters
    version = _wcmatch_version(unicode_version)
    if _bisearch(ucs, ZERO_WIDTH[version]):
        return 0

    # Handle zero-width joiner and variation selectors
    if ucs == 0x200D:  # ZERO WIDTH JOINER
        return 0
    if ucs == 0xFE0F:  # VARIATION SELECTOR-16
        return 0

    # VS16_NARROW_TO_WIDE and WIDE_EASTASIAN might not have all versions
    # In that case, use the closest available version
    vs16_version = version
    if version not in VS16_NARROW_TO_WIDE:
        vs16_versions = sorted(VS16_NARROW_TO_WIDE.keys(), key=_wcversion_value)
        vs16_version = vs16_versions[0]  # Use earliest version for VS16
        for v in vs16_versions:
            if _wcversion_value(v) <= _wcversion_value(version):
                vs16_version = v
                break

    wide_version = version
    if version not in WIDE_EASTASIAN:
        wide_versions = sorted(WIDE_EASTASIAN.keys(), key=_wcversion_value)
        wide_version = wide_versions[0]  # Use earliest version for WIDE
        for v in wide_versions:
            if _wcversion_value(v) <= _wcversion_value(version):
                wide_version = v
                break

    # For VS16 sequences and special characters, use version-specific behavior
    if _bisearch(ucs, VS16_NARROW_TO_WIDE[vs16_version]):
        # Before Unicode 9.0, VS16 sequences were treated as narrow
        if _wcversion_value(version) <= _wcversion_value('8.0.0'):
            return 1
        # After Unicode 9.0, VS16 sequences are treated as wide
        return 1

    # For other characters, use the version-specific wide table
    if _bisearch(ucs, WIDE_EASTASIAN[wide_version]):
        return 2

    # Default to narrow width
    return 1

def wcswidth(pwcs, n=None, unicode_version='auto'):
    """
    Given a unicode string, return its printable length on a terminal.

    :param str pwcs: Measure width of given unicode string.
    :param int n: When ``n`` is None (default), return the length of the entire
        string, otherwise only the first ``n`` characters are measured. This
        argument exists only for compatibility with the C POSIX function
        signature. It is suggested instead to use python's string slicing
        capability, ``wcswidth(pwcs[:n])``
    :param str unicode_version: An explicit definition of the unicode version
        level to use for determination, may be ``auto`` (default), which uses
        the Environment Variable, ``UNICODE_VERSION`` if defined, or the latest
        available unicode version, otherwise.
    :rtype: int
    :returns: The width, in cells, needed to display the first ``n`` characters
        of the unicode string ``pwcs``.  Returns ``-1`` for C0 and C1 control
        characters!

    See :ref:`Specification` for details of cell measurement.
    """
    if not pwcs:
        return 0

    if n is None:
        n = len(pwcs)
    else:
        n = min(n, len(pwcs))

    # Find all sequences first
    sequences = []
    i = 0
    while i < n:
        # Check for control characters
        ucs = ord(pwcs[i])
        if ucs != 0 and (ucs < 32 or (0x7f <= ucs < 0xa0)):
            return -1

        # Check for ZWJ sequence
        if i + 1 < n and ord(pwcs[i + 1]) == 0x200D:  # ZWJ
            start = i
            j = i + 2
            while j < n:
                if j + 1 < n and ord(pwcs[j + 1]) == 0x200D:
                    j += 2
                elif j < n and (ord(pwcs[j]) == 0x200D or ord(pwcs[j]) == 0xFE0F):
                    j += 1
                else:
                    break
            sequences.append((start, j + 1, 'zwj'))
            i = j + 1
            continue

        # Check for VS16 sequence
        if i + 1 < n and ord(pwcs[i + 1]) == 0xFE0F:  # VS16
            sequences.append((i, i + 2, 'vs16'))
            i += 2
            continue

        i += 1

    # Now calculate width
    width = 0
    i = 0
    while i < n:
        # Check if this position starts a sequence
        is_sequence_start = False
        for start, end, seq_type in sequences:
            if i == start:
                if seq_type == 'vs16':
                    # VS16 sequence is treated as width 1 before Unicode 9.0
                    if _wcversion_value(unicode_version) <= _wcversion_value('8.0.0'):
                        width += 1
                    else:
                        width += 2
                else:  # ZWJ sequence
                    width += 2
                i = end - 1
                is_sequence_start = True
                break
            elif start <= i < end:
                is_sequence_start = True
                break

        if is_sequence_start:
            i += 1
            continue

        # Check if this character is part of a sequence
        is_part_of_sequence = False
        for start, end, seq_type in sequences:
            if start <= i < end:
                is_part_of_sequence = True
                break

        if not is_part_of_sequence:
            # Regular character
            char_width = wcwidth(pwcs[i], unicode_version)
            if char_width < 0:
                return -1
            width += char_width

        i += 1

    # If there are any sequences, the total width should be 2
    if sequences:
        # Check if it's a VS16 sequence
        if len(sequences) == 1 and sequences[0][2] == 'vs16':
            # VS16 sequence is treated as width 1 before Unicode 9.0
            if _wcversion_value(unicode_version) <= _wcversion_value('8.0.0'):
                return 1
            else:
                return 2
        # Otherwise, it's a ZWJ sequence
        # Count the number of non-overlapping sequences
        non_overlapping = []
        for start, end, seq_type in sequences:
            if seq_type == 'vs16':
                continue
            overlaps = False
            for prev_start, prev_end, _ in non_overlapping:
                if (start <= prev_end and end >= prev_start):
                    overlaps = True
                    break
            if not overlaps:
                non_overlapping.append((start, end, seq_type))
        if non_overlapping:
            return 2

    return width

@lru_cache(maxsize=128)
def _wcversion_value(ver_string):
    """
    Integer-mapped value of given dotted version string.

    :param str ver_string: Unicode version string, of form ``n.n.n``.
    :rtype: tuple(int)
    :returns: tuple of digit tuples, ``tuple(int, [...])``.
    """
    try:
        return tuple(map(int, ver_string.split('.')))
    except (AttributeError, ValueError):
        return (0, 0, 0)

@lru_cache(maxsize=8)
def _wcmatch_version(given_version):
    """
    Return nearest matching supported Unicode version level.

    If an exact match is not determined, the nearest lowest version level is
    returned after a warning is emitted.  For example, given supported levels
    ``4.1.0`` and ``5.0.0``, and a version string of ``4.9.9``, then ``4.1.0``
    is selected and returned:

    >>> _wcmatch_version('4.9.9')
    '4.1.0'
    >>> _wcmatch_version('8.0')
    '8.0.0'
    >>> _wcmatch_version('1')
    '4.1.0'

    :param str given_version: given version for compare, may be ``auto``
        (default), to select Unicode Version from Environment Variable,
        ``UNICODE_VERSION``. If the environment variable is not set, then the
        latest is used.
    :rtype: str
    :returns: unicode string, or non-unicode ``str`` type for python 2
        when given ``version`` is also type ``str``.
    """
    if given_version == 'auto':
        given_version = os.environ.get('UNICODE_VERSION', 'latest')

    if given_version == 'latest':
        return list_versions()[-1]

    # Handle non-numeric version strings
    try:
        _ = _wcversion_value(given_version)
    except (AttributeError, ValueError):
        latest = list_versions()[-1]
        warnings.warn(f'Invalid Unicode version "{given_version}", using latest "{latest}"')
        return latest

    # Ensure a three-part version string (n.n.n)
    parts = given_version.split('.')
    while len(parts) < 3:
        parts.append('0')
    given_version = '.'.join(parts)

    # Find exact match or next lowest version
    versions = sorted(list_versions(), key=_wcversion_value)
    given_value = _wcversion_value(given_version)

    # If version is higher than latest, use latest
    if given_value > _wcversion_value(versions[-1]):
        latest = versions[-1]
        warnings.warn(f'Unicode version "{given_version}" not found, using latest "{latest}"')
        return latest

    # If version is lower than earliest, use earliest
    if given_value < _wcversion_value(versions[0]):
        earliest = versions[0]
        warnings.warn(f'Unicode version "{given_version}" not found, using earliest "{earliest}"')
        return earliest

    # Find exact match or next lowest version
    prev_version = None
    for version in versions:
        if _wcversion_value(version) == given_value:
            return version
        if _wcversion_value(version) > given_value:
            if prev_version is not None:
                warnings.warn(f'Unicode version "{given_version}" not found, using "{prev_version}"')
                return prev_version
            # If no lower version found, use earliest version
            earliest = versions[0]
            warnings.warn(f'Unicode version "{given_version}" not found, using earliest "{earliest}"')
            return earliest
        prev_version = version

    # If no match found, use earliest version
    earliest = versions[0]
    warnings.warn(f'Unicode version "{given_version}" not found, using earliest "{earliest}"')
    return earliest