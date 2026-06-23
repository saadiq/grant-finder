from dataclasses import dataclass


@dataclass
class OrgProfile:
    ein: str
    name: str
    ntee: str
    city: str
    state: str
    revenue: int | None


@dataclass
class Peer:
    ein: str
    name: str
    ntee: str
    city: str
    state: str


@dataclass
class GrantEdge:
    funder_ein: str
    funder_name: str
    funder_type: str          # '990PF' | '990' | '990EZ'
    recipient_name: str
    recipient_ein: str        # '' when unknown (always '' at parse time for 990-PF)
    recipient_city: str
    recipient_state: str
    purpose: str
    amount: int | None
    source: str               # 'PF-grant' | 'SchedI'
    tax_year: int | None
    resolved_score: float | None


@dataclass
class FunderProspect:
    funder_ein: str
    funder_name: str
    funder_type: str
    n_peers: int
    total_amount: int
    recent_year: int | None
    purposes: list[str]
    score: float
