"""
Ottoneu league-related API endpoints
"""

from flask import Blueprint, jsonify, request
from backend.data_sources.ottoneu import OttoneuClient
from config import Config

bp = Blueprint('league', __name__)


def get_client():
    """Get Ottoneu client, optionally with league_id from request."""
    league_id = request.args.get('league_id', Config.OTTONEU_LEAGUE_ID)
    return OttoneuClient(league_id=league_id)


def df_to_json(df, limit=None):
    """Convert DataFrame to JSON-serializable list of dicts."""
    if df.empty:
        return []
    if limit:
        df = df.head(limit)
    return df.to_dict(orient='records')


@bp.route('/info', methods=['GET'])
def get_league_info():
    """Get basic league information."""
    try:
        client = get_client()
        info = client.get_league_info()
        return jsonify(info)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch league info: {str(e)}'}), 500


@bp.route('/teams', methods=['GET'])
def get_teams():
    """
    Get all teams in the league with their names and IDs.

    Query params:
        league_id: Override configured league ID
    """
    try:
        client = get_client()

        # Use the new get_teams method which extracts from roster data
        teams = client.get_teams()

        return jsonify({
            'league_id': request.args.get('league_id', Config.OTTONEU_LEAGUE_ID),
            'teams': teams,
            'count': len(teams)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch teams: {str(e)}'}), 500


@bp.route('/roster', methods=['GET'])
def get_roster():
    """
    Get roster for a specific team.

    Query params:
        team_id: Ottoneu team ID (optional, returns all if not specified)
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        team_id = request.args.get('team_id', type=int)

        if team_id:
            roster = client.get_my_roster(team_id=team_id)
        else:
            roster = client.get_league_rosters()

        return jsonify({
            'roster': df_to_json(roster),
            'count': len(roster)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch roster: {str(e)}'}), 500


@bp.route('/players', methods=['GET'])
def get_league_players():
    """
    Get all players in the league with ownership and salary info.

    Query params:
        position: Filter by position (e.g., 'SP', '1B')
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        position = request.args.get('position')

        if position:
            players = client.get_roster_by_position(position)
        else:
            players = client.get_league_rosters()

        return jsonify({
            'players': df_to_json(players),
            'count': len(players)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch players: {str(e)}'}), 500


@bp.route('/free-agents', methods=['GET'])
def get_free_agents():
    """
    Get available free agents.

    Query params:
        position: Filter by position (e.g., 'SP', '1B', 'OF')
        limit: Max number of results (default 100)
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        position = request.args.get('position')
        limit = request.args.get('limit', 100, type=int)

        free_agents = client.get_free_agents(position=position)

        return jsonify({
            'position_filter': position,
            'free_agents': df_to_json(free_agents, limit=limit),
            'count': len(free_agents),
            'showing': min(limit, len(free_agents))
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch free agents: {str(e)}'}), 500


@bp.route('/standings', methods=['GET'])
def get_standings():
    """
    Get current league standings.

    Query params:
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        standings = client.get_league_standings()

        return jsonify({
            'standings': df_to_json(standings),
            'count': len(standings)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch standings: {str(e)}'}), 500


@bp.route('/transactions', methods=['GET'])
def get_transactions():
    """
    Get recent league transactions.

    Query params:
        days: Number of days to look back (default 7)
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        days = request.args.get('days', 7, type=int)

        transactions = client.get_recent_transactions(days=days)

        return jsonify({
            'days': days,
            'transactions': df_to_json(transactions),
            'count': len(transactions)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch transactions: {str(e)}'}), 500


@bp.route('/salaries', methods=['GET'])
def get_salaries():
    """
    Get salary information across the league, sorted by salary.

    Query params:
        position: Filter by position
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        position = request.args.get('position')

        rosters = client.get_league_rosters()

        if position and not rosters.empty:
            rosters = rosters[
                rosters['position'].str.contains(position, case=False, na=False)
            ]

        # Sort by salary descending
        if not rosters.empty and 'salary' in rosters.columns:
            rosters = rosters.sort_values('salary', ascending=False)

        return jsonify({
            'salaries': df_to_json(rosters),
            'count': len(rosters)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch salaries: {str(e)}'}), 500


@bp.route('/values', methods=['GET'])
def get_values():
    """
    Get player surplus values (average value - salary).

    Query params:
        min_surplus: Minimum surplus value to include
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        min_surplus = request.args.get('min_surplus', type=float)

        values = client.calculate_surplus_values()

        if min_surplus and not values.empty:
            values = values[values['surplus'] >= min_surplus]

        return jsonify({
            'values': df_to_json(values),
            'count': len(values)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to calculate values: {str(e)}'}), 500


@bp.route('/average-values', methods=['GET'])
def get_average_values():
    """
    Get average auction values across all Ottoneu leagues.

    Query params:
        format: Scoring format ID (1=FGPts, 2=SABR, 3=4x4, 4=5x5)
        position: Filter by position
        limit: Max results (default 100)
    """
    try:
        client = get_client()
        scoring_format = request.args.get('format', type=int)
        position = request.args.get('position')
        limit = request.args.get('limit', 100, type=int)

        avg_values = client.get_average_values(scoring_format=scoring_format)

        if position and not avg_values.empty and 'position' in avg_values.columns:
            avg_values = avg_values[
                avg_values['position'].str.contains(position, case=False, na=False)
            ]

        return jsonify({
            'average_values': df_to_json(avg_values, limit=limit),
            'count': len(avg_values),
            'showing': min(limit, len(avg_values))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch average values: {str(e)}'}), 500


@bp.route('/player/<int:player_id>', methods=['GET'])
def get_player_info(player_id):
    """
    Get detailed info for a specific player.

    Query params:
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        player_info = client.get_player_info(player_id)

        return jsonify(player_info)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch player info: {str(e)}'}), 500


@bp.route('/player/<int:player_id>/history', methods=['GET'])
def get_player_history(player_id):
    """
    Get salary history for a specific player.

    Query params:
        league_id: Override configured league ID
    """
    try:
        client = get_client()
        history = client.get_player_salary_history(player_id)

        return jsonify({
            'player_id': player_id,
            'history': df_to_json(history)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch salary history: {str(e)}'}), 500


@bp.route('/search', methods=['GET'])
def search_players():
    """
    Search for players by name.

    Query params:
        q: Search query (required)
        limit: Max results (default 25)
    """
    query = request.args.get('q', '')
    limit = request.args.get('limit', 25, type=int)

    if not query:
        return jsonify({'error': 'Search query (q) is required'}), 400

    try:
        client = get_client()
        results = client.search_players(query)

        return jsonify({
            'query': query,
            'results': df_to_json(results, limit=limit),
            'count': len(results),
            'showing': min(limit, len(results))
        })
    except Exception as e:
        return jsonify({'error': f'Search failed: {str(e)}'}), 500
