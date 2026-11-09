# DEV-02: Incorrect revenue-growth claim

The request says SYNBB revenue grew 30%. The synthetic records show revenue of
USD 100 million in FY2024 and USD 110 million in FY2025, a 10% increase.

[inputs.json](inputs.json) supplies the request, user context, fixed account, and
two XBRL-shaped facts. [reference.json](reference.json) holds the calculation,
response criteria, and two direct matcher probes: USD 110 million is supported;
USD 130 million is contradicted.

The matcher compares individual tagged facts. It does not derive growth from two
records, so the 10% growth calculation is an independent evaluation reference.
An answer may correct the premise and ask for more evidence before discussing a
trade. Buying is not required.

This development case is separate from the ten pilot candidates. All records
are synthetic, and no API call is needed to load or check them.
