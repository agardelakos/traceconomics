"""Code that reads microdata and therefore runs only on the owner's machine.

The code is public; the data it reads never are. It needs the optional
`local` dependencies (`pip install -e .[local]`). Everything it writes is
aggregated: group totals and shares, never a household's record.
"""
