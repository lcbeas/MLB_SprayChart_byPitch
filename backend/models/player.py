"""
Player data model
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class Player:
    """Represents a baseball player with combined data from multiple sources."""

    # Identifiers
    name: str
    mlbam_id: Optional[int] = None
    fangraphs_id: Optional[int] = None
    ottoneu_id: Optional[int] = None

    # Basic info
    team: Optional[str] = None
    position: Optional[str] = None
    positions: List[str] = field(default_factory=list)
    bats: Optional[str] = None  # L, R, S
    throws: Optional[str] = None  # L, R

    # Ottoneu info
    salary: Optional[float] = None
    owner: Optional[str] = None  # Team name in league

    # Stats
    stats: Dict = field(default_factory=dict)

    # Projections
    projections: Dict = field(default_factory=dict)

    # Statcast
    statcast: Dict = field(default_factory=dict)

    # Calculated values
    projected_value: Optional[float] = None
    surplus_value: Optional[float] = None  # projected_value - salary

    def __post_init__(self):
        """Calculate derived fields after initialization."""
        if self.projected_value and self.salary:
            self.surplus_value = self.projected_value - self.salary

    @property
    def is_free_agent(self) -> bool:
        """Check if player is a free agent (unowned)."""
        return self.owner is None

    @property
    def is_hitter(self) -> bool:
        """Check if player is a position player."""
        pitcher_positions = {'SP', 'RP', 'P'}
        return not any(pos in pitcher_positions for pos in self.positions)

    @property
    def is_pitcher(self) -> bool:
        """Check if player is a pitcher."""
        pitcher_positions = {'SP', 'RP', 'P'}
        return any(pos in pitcher_positions for pos in self.positions)

    def to_dict(self) -> Dict:
        """Convert player to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'mlbam_id': self.mlbam_id,
            'fangraphs_id': self.fangraphs_id,
            'team': self.team,
            'position': self.position,
            'positions': self.positions,
            'salary': self.salary,
            'owner': self.owner,
            'projected_value': self.projected_value,
            'surplus_value': self.surplus_value,
            'is_free_agent': self.is_free_agent,
            'stats': self.stats,
            'projections': self.projections,
            'statcast': self.statcast
        }
