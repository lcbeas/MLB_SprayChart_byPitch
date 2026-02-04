"""
Team data model
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional

from .player import Player


@dataclass
class Team:
    """Represents a team in an Ottoneu league."""

    name: str
    team_id: Optional[int] = None
    roster: List[Player] = field(default_factory=list)

    @property
    def total_salary(self) -> float:
        """Calculate total salary committed to roster."""
        return sum(p.salary or 0 for p in self.roster)

    @property
    def roster_size(self) -> int:
        """Get number of players on roster."""
        return len(self.roster)

    @property
    def cap_space(self, cap: float = 400.0) -> float:
        """Calculate remaining cap space."""
        return cap - self.total_salary

    @property
    def hitters(self) -> List[Player]:
        """Get all hitters on the roster."""
        return [p for p in self.roster if p.is_hitter]

    @property
    def pitchers(self) -> List[Player]:
        """Get all pitchers on the roster."""
        return [p for p in self.roster if p.is_pitcher]

    def get_players_by_position(self, position: str) -> List[Player]:
        """Get all players eligible at a specific position."""
        return [p for p in self.roster if position in p.positions]

    def total_projected_value(self) -> float:
        """Calculate total projected value of roster."""
        return sum(p.projected_value or 0 for p in self.roster)

    def total_surplus_value(self) -> float:
        """Calculate total surplus value of roster."""
        return sum(p.surplus_value or 0 for p in self.roster)

    def to_dict(self) -> Dict:
        """Convert team to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'team_id': self.team_id,
            'roster': [p.to_dict() for p in self.roster],
            'total_salary': self.total_salary,
            'roster_size': self.roster_size,
            'total_projected_value': self.total_projected_value(),
            'total_surplus_value': self.total_surplus_value()
        }
