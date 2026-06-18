"""
Proto-Elamite structural analyzer.
Parses CDLI ATF for the proto-elamite script (lang qpc) and extracts
administrative structure: headers, commodity entries, numerical totals,
sign frequencies, and co-occurrence patterns.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# Numerical weight table (approximate).
# Proto-Elamite used multiple metrological systems side-by-side.
# These ratios are relative to N01 within each system.
# ------------------------------------------------------------------
_NUMERAL_SYSTEMS: dict[str, dict[str, float]] = {
    "counting": {   # discrete objects / animals / people
        "N01": 1,
        "N14": 10,
        "N34": 60,
        "N45": 120,
        "N48": 1200,
    },
    "grain": {      # capacity measures
        "N30C": 1,
        "N24":  6,
        "N39B": 18,
        "N30B": 180,
        "N30A": 1800,
    },
    "area": {
        "N08A": 1,
        "N08B": 6,
        "N08C": 60,
    },
    "time?": {
        "N50": 1,
    },
}
# Flat map: N-token → (system, weight)
_N_TOKEN_INFO: dict[str, tuple[str, float]] = {}
for _sys, _vals in _NUMERAL_SYSTEMS.items():
    for _tok, _wt in _vals.items():
        _N_TOKEN_INFO[_tok] = (_sys, _wt)


# ------------------------------------------------------------------
# ATF parser
# ------------------------------------------------------------------
_SIGN_RE  = re.compile(r'\|?[A-Z][A-Z0-9~\+\|]*\|?(?:[~@][a-z0-9]+)?')
_M_RE     = re.compile(r'M\d+(?:[~@][a-z0-9]+)?|\|M\d+[^|]*\|')
_N_RE     = re.compile(r'(\d+)\((N[^)]+)\)')
_LINE_RE  = re.compile(r"^(\d+)'?\.\s+(.*)")


@dataclass
class AtfEntry:
    line_no:   str
    raw:       str
    signs:     list[str]            # M-signs (commodity side)
    numerals:  list[tuple[int, str]] # [(count, N-token), ...]
    is_header: bool   = False       # line with sign(s) but no numerals
    is_total:  bool   = False       # reverse total (heuristic)
    surface:   str    = "obverse"   # obverse / reverse / top / …
    column:    int    = 1


@dataclass
class TabletAnalysis:
    p_number:    str
    designation: str
    atf:         str
    entries:     list[AtfEntry] = field(default_factory=list)

    # --- derived stats ---
    sign_freq:   dict[str, int] = field(default_factory=dict)
    cooccur:     dict[str, dict[str, int]] = field(default_factory=dict)
    n_system_freq: dict[str, int] = field(default_factory=dict)
    n_token_freq:  dict[str, int] = field(default_factory=dict)

    # computed totals vs sum-of-entries discrepancy
    declared_totals: list[dict] = field(default_factory=list)
    entry_sums:      dict[str, float] = field(default_factory=dict)

    # administrative pattern classification
    pattern: str = "unknown"      # ledger | ration-list | list | unknown
    n_entries: int = 0
    n_header_signs: int = 0

    def to_dict(self) -> dict:
        return {
            "p_number":      self.p_number,
            "designation":   self.designation,
            "pattern":       self.pattern,
            "n_entries":     self.n_entries,
            "n_header_signs": self.n_header_signs,
            "sign_freq":     sorted(self.sign_freq.items(), key=lambda x: -x[1]),
            "n_system_freq": dict(self.n_system_freq),
            "n_token_freq":  sorted(self.n_token_freq.items(), key=lambda x: -x[1]),
            "cooccur":       {k: dict(v) for k, v in self.cooccur.items()},
            "declared_totals": self.declared_totals,
            "entry_sums":    dict(self.entry_sums),
            "entries": [
                {
                    "line_no":   e.line_no,
                    "surface":   e.surface,
                    "column":    e.column,
                    "signs":     e.signs,
                    "numerals":  [{"count": c, "token": t} for c, t in e.numerals],
                    "is_header": e.is_header,
                    "is_total":  e.is_total,
                }
                for e in self.entries
            ],
        }


def parse_atf(p_number: str, designation: str, atf: str) -> TabletAnalysis:
    ta = TabletAnalysis(p_number=p_number, designation=designation, atf=atf)
    surface = "obverse"
    column  = 1

    for raw_line in atf.splitlines():
        line = raw_line.strip()
        # surface / column markers
        if line.startswith("@obverse"):
            surface = "obverse"
        elif line.startswith("@reverse"):
            surface = "reverse"
        elif line.startswith("@top"):
            surface = "top"
        elif line.startswith("@left") or line.startswith("@bottom"):
            surface = line.lstrip("@").split()[0]
        elif line.startswith("@column"):
            try:
                column = int(line.split()[1])
            except (IndexError, ValueError):
                pass
        elif line.startswith("#") or line.startswith("&") or line.startswith("$"):
            continue  # comments, headers, state lines

        m = _LINE_RE.match(line)
        if not m:
            continue

        line_no  = m.group(1)
        content  = m.group(2)

        # Split at comma into sign-side and numeral-side
        if "," in content:
            sign_side, num_side = content.split(",", 1)
        else:
            sign_side, num_side = content, ""

        # Strip damage markers (#, ?, [, ])
        sign_side_clean = re.sub(r'[#?\[\]]', '', sign_side)
        signs = _M_RE.findall(sign_side_clean)
        # Normalise: strip variant suffixes after ~ for uniqueness check
        signs = [s.split("~")[0].strip("|") for s in signs]
        signs = [s for s in signs if s]  # remove empties

        numerals = []
        for cnt_str, n_tok in _N_RE.findall(num_side):
            numerals.append((int(cnt_str), n_tok))

        is_header = bool(signs) and not numerals
        is_total  = (surface == "reverse") and bool(numerals) and not any(
            e.signs == signs and e.surface == "obverse" for e in ta.entries
        )

        entry = AtfEntry(
            line_no=line_no, raw=raw_line,
            signs=signs, numerals=numerals,
            is_header=is_header, is_total=is_total,
            surface=surface, column=column,
        )
        ta.entries.append(entry)

    _compute_stats(ta)
    return ta


def _compute_stats(ta: TabletAnalysis) -> None:
    sign_freq:   Counter[str]              = Counter()
    n_tok_freq:  Counter[str]              = Counter()
    n_sys_freq:  Counter[str]              = Counter()
    cooccur: dict[str, Counter[str]]       = defaultdict(Counter)
    entry_sums: dict[str, float]           = defaultdict(float)
    declared_totals: list[dict]            = []

    data_entries  = [e for e in ta.entries if not e.is_header and e.numerals]
    header_signs  = [e for e in ta.entries if e.is_header]

    for entry in ta.entries:
        for s in entry.signs:
            sign_freq[s] += 1

        for cnt, n_tok in entry.numerals:
            n_tok_freq[n_tok] += cnt
            sys_name = _N_TOKEN_INFO.get(n_tok, (None, 1))[0]
            if sys_name:
                n_sys_freq[sys_name] += cnt
            # tally into entry_sums keyed by N-system
            wt = _N_TOKEN_INFO.get(n_tok, (None, 1))[1]
            key = sys_name or "unknown"
            if not entry.is_total:
                entry_sums[key] += cnt * wt

        # co-occurrence within line
        signs = entry.signs
        for i, s1 in enumerate(signs):
            for s2 in signs[i+1:]:
                cooccur[s1][s2] += 1
                cooccur[s2][s1] += 1

        # track declared totals (reverse totals)
        if entry.is_total:
            declared_totals.append({
                "surface": entry.surface,
                "signs":   entry.signs,
                "numerals": [{"count": c, "token": t} for c, t in entry.numerals],
            })

    ta.sign_freq      = dict(sign_freq)
    ta.n_token_freq   = dict(n_tok_freq)
    ta.n_system_freq  = dict(n_sys_freq)
    ta.cooccur        = {k: dict(v) for k, v in cooccur.items()}
    ta.entry_sums     = dict(entry_sums)
    ta.declared_totals = declared_totals
    ta.n_entries      = len(data_entries)
    ta.n_header_signs = len(header_signs)

    # Classify administrative pattern
    if header_signs and data_entries:
        if len(data_entries) >= 3:
            # Count how many unique sign-groups vs. repeated
            sign_tuples = [tuple(e.signs) for e in data_entries]
            uniq = len(set(sign_tuples))
            if uniq == len(sign_tuples):
                ta.pattern = "ledger"        # each row is a different commodity
            else:
                ta.pattern = "ration-list"   # repeated commodity, varying amounts
        else:
            ta.pattern = "list"
    elif data_entries and not header_signs:
        ta.pattern = "list"
    else:
        ta.pattern = "unknown"


# ------------------------------------------------------------------
# Corpus-level analysis across multiple tablets
# ------------------------------------------------------------------
def corpus_summary(analyses: list[TabletAnalysis]) -> dict:
    global_sign_freq: Counter[str] = Counter()
    global_n_sys: Counter[str]     = Counter()
    global_n_tok: Counter[str]     = Counter()
    pattern_dist: Counter[str]     = Counter()

    for ta in analyses:
        global_sign_freq.update(ta.sign_freq)
        global_n_sys.update(ta.n_system_freq)
        global_n_tok.update(ta.n_token_freq)
        pattern_dist[ta.pattern] += 1

    # Top co-occurring sign pairs across corpus
    pair_freq: Counter[tuple[str, str]] = Counter()
    for ta in analyses:
        for s1, partners in ta.cooccur.items():
            for s2, cnt in partners.items():
                if s1 < s2:  # avoid double-counting
                    pair_freq[(s1, s2)] += cnt

    return {
        "n_tablets": len(analyses),
        "top_signs": global_sign_freq.most_common(30),
        "n_system_dist": dict(global_n_sys),
        "top_n_tokens": global_n_tok.most_common(20),
        "pattern_dist": dict(pattern_dist),
        "top_cooccur_pairs": [
            {"signs": list(pair), "count": cnt}
            for pair, cnt in pair_freq.most_common(20)
        ],
    }
