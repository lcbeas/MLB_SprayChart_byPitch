"""
Ottoneu league-related API endpoints
"""

from flask import Blueprint, jsonify, request
from backend.data_sources import ottoneu

bp = Blueprint('league', __name__)


@bp.route('/roster', methods=['GET'])
def get_roster():
    """Get the current roster for your team."""
    # TODO: Implement roster fetching from Ottoneu
    return jsonify({
        'roster': [],
        'message': 'Roster endpoint - implementation pending'
    })


@bp.route('/players', methods=['GET'])
def get_league_players():
    """Get all players in the league with ownership and salary info."""
    # TODO: Implement league player data
    return jsonify({
        'players': [],
        'message': 'League players endpoint - implementation pending'
    })


@bp.route('/free-agents', methods=['GET'])
def get_free_agents():
    """Get available free agents."""
    position = request.args.get('position', None)
    # TODO: Implement free agent listing
    return jsonify({
        'position_filter': position,
        'free_agents': [],
        'message': 'Free agents endpoint - implementation pending'
    })


@bp.route('/salaries', methods=['GET'])
def get_salaries():
    """Get salary information across the league."""
    # TODO: Implement salary data
    return jsonify({
        'salaries': [],
        'message': 'Salaries endpoint - implementation pending'
    })


@bp.route('/values', methods=['GET'])
def get_values():
    """Get player values (surplus value = projected value - salary)."""
    # TODO: Implement value calculations
    return jsonify({
        'values': [],
        'message': 'Values endpoint - implementation pending'
    })
