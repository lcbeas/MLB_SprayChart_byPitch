"""
Analysis API endpoints

Exposes roster analysis and trade analysis functionality.
"""

from flask import Blueprint, jsonify, request
from backend.analysis.roster_analyzer import RosterAnalyzer
from backend.analysis.trade_analyzer import TradeAnalyzer
from config import Config

bp = Blueprint('analysis', __name__)


def get_roster_analyzer():
    """Get RosterAnalyzer with configured league."""
    league_id = request.args.get('league_id', Config.OTTONEU_LEAGUE_ID)
    return RosterAnalyzer(league_id=league_id)


def get_trade_analyzer():
    """Get TradeAnalyzer with configured league."""
    league_id = request.args.get('league_id', Config.OTTONEU_LEAGUE_ID)
    return TradeAnalyzer(league_id=league_id)


# -----------------------------------------------------------------------------
# Roster Analysis Endpoints
# -----------------------------------------------------------------------------

@bp.route('/roster/analyze', methods=['GET'])
def analyze_roster():
    """
    Comprehensive roster analysis.

    Query params:
        team_id: Your Ottoneu team ID (required)
        league_id: Override configured league ID
        compare_to: 'league' or 'top_teams' (default: 'league')

    Returns:
        Roster analysis including:
        - Overall roster score (A-F grade)
        - Positional analysis
        - League comparison
        - Top team comparison
        - Identified weaknesses
        - Buy low / sell high opportunities
        - Recommendations
    """
    team_id = request.args.get('team_id', type=int)
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400

    compare_to = request.args.get('compare_to', 'league')

    try:
        analyzer = get_roster_analyzer()
        analysis = analyzer.analyze_roster(team_id, compare_to=compare_to)

        if 'error' in analysis:
            return jsonify(analysis), 400

        return jsonify(analysis)
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@bp.route('/roster/positions', methods=['GET'])
def get_positional_analysis():
    """
    Get detailed positional analysis for your roster.

    Query params:
        team_id: Your Ottoneu team ID (required)
        league_id: Override configured league ID
    """
    team_id = request.args.get('team_id', type=int)
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400

    try:
        analyzer = get_roster_analyzer()
        analysis = analyzer.analyze_roster(team_id)

        return jsonify({
            'team_id': team_id,
            'positional_analysis': analysis.get('positional_analysis', {}),
            'weaknesses': analysis.get('weaknesses', []),
        })
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@bp.route('/roster/rankings/<position>', methods=['GET'])
def get_position_rankings(position):
    """
    Get league-wide rankings for a specific position.

    Path params:
        position: Position to rank (C, 1B, 2B, SS, 3B, OF, SP, RP)

    Query params:
        league_id: Override configured league ID
        limit: Max results (default: 50)
    """
    limit = request.args.get('limit', 50, type=int)

    try:
        analyzer = get_roster_analyzer()
        rankings = analyzer.get_positional_rankings(position.upper())

        if rankings.empty:
            return jsonify({
                'position': position,
                'rankings': [],
                'count': 0
            })

        # Convert to JSON-safe format
        rankings_list = rankings.head(limit).fillna('').to_dict('records')

        return jsonify({
            'position': position,
            'rankings': rankings_list,
            'count': len(rankings),
            'showing': min(limit, len(rankings))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get rankings: {str(e)}'}), 500


@bp.route('/roster/score', methods=['GET'])
def get_roster_score():
    """
    Get quick roster score (A-F grade) without full analysis.

    Query params:
        team_id: Your Ottoneu team ID (required)
        league_id: Override configured league ID
    """
    team_id = request.args.get('team_id', type=int)
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400

    try:
        analyzer = get_roster_analyzer()
        analysis = analyzer.analyze_roster(team_id)

        return jsonify({
            'team_id': team_id,
            'roster_score': analysis.get('roster_score', {}),
        })
    except Exception as e:
        return jsonify({'error': f'Scoring failed: {str(e)}'}), 500


@bp.route('/roster/recommendations', methods=['GET'])
def get_roster_recommendations():
    """
    Get prioritized recommendations for roster improvement.

    Query params:
        team_id: Your Ottoneu team ID (required)
        league_id: Override configured league ID
    """
    team_id = request.args.get('team_id', type=int)
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400

    try:
        analyzer = get_roster_analyzer()
        analysis = analyzer.analyze_roster(team_id)

        return jsonify({
            'team_id': team_id,
            'recommendations': analysis.get('recommendations', []),
            'weaknesses': analysis.get('weaknesses', []),
            'value_opportunities': analysis.get('value_opportunities', {}),
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get recommendations: {str(e)}'}), 500


# -----------------------------------------------------------------------------
# Trade Analysis Endpoints
# -----------------------------------------------------------------------------

@bp.route('/trade/evaluate', methods=['POST'])
def evaluate_trade():
    """
    Evaluate a proposed trade.

    POST body (simple format from frontend):
        {
            "team_id": 123,
            "give_players": [...],
            "get_players": [...]
        }

    Or full format:
        {
            "my_team_id": 123,
            "my_players": [...],
            "their_team_id": 789,
            "their_players": [...]
        }

    Query params:
        league_id: Override configured league ID

    Returns:
        Trade evaluation with fairness rating, value analysis, and recommendation
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    # Support both simple frontend format and full format
    my_team_id = data.get('my_team_id') or data.get('team_id')
    my_players = data.get('my_players') or data.get('give_players', [])
    their_team_id = data.get('their_team_id') or 0  # Can be 0 if not specified
    their_players = data.get('their_players') or data.get('get_players', [])

    if not my_team_id:
        return jsonify({'error': 'team_id is required'}), 400

    if not my_players or not their_players:
        return jsonify({'error': 'Both give_players and get_players are required'}), 400

    try:
        analyzer = get_trade_analyzer()
        evaluation = analyzer.evaluate_trade(
            my_team_id=my_team_id,
            my_players=my_players,
            their_team_id=their_team_id,
            their_players=their_players
        )

        return jsonify(evaluation)
    except Exception as e:
        return jsonify({'error': f'Evaluation failed: {str(e)}'}), 500


@bp.route('/trade/targets', methods=['GET'])
def find_trade_targets():
    """
    Find potential trade targets on other teams.

    Query params:
        team_id: Your Ottoneu team ID (required)
        position: Target position to filter (optional)
        max_salary: Maximum salary to consider (optional)
        league_id: Override configured league ID
        limit: Max results (default: 50)
    """
    team_id = request.args.get('team_id', type=int)
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400

    position = request.args.get('position')
    max_salary = request.args.get('max_salary', type=float)
    limit = request.args.get('limit', 50, type=int)

    try:
        analyzer = get_trade_analyzer()
        targets = analyzer.find_trade_targets(
            my_team_id=team_id,
            target_position=position,
            max_salary=max_salary
        )

        return jsonify({
            'team_id': team_id,
            'position_filter': position,
            'max_salary_filter': max_salary,
            'targets': targets[:limit],
            'count': len(targets),
            'showing': min(limit, len(targets))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to find targets: {str(e)}'}), 500


@bp.route('/trade/find-fair', methods=['GET'])
def find_fair_trades():
    """
    Find fair trade packages to acquire a specific player.

    Query params:
        team_id: Your Ottoneu team ID (required)
        target_player_id: Player you want to acquire (required)
        max_players: Max players you'll give up (default: 2)
        league_id: Override configured league ID
    """
    team_id = request.args.get('team_id', type=int)
    target_player_id = request.args.get('target_player_id', type=int)

    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400
    if not target_player_id:
        return jsonify({'error': 'target_player_id is required'}), 400

    max_players = request.args.get('max_players', 2, type=int)

    try:
        analyzer = get_trade_analyzer()
        trades = analyzer.find_fair_trades(
            my_team_id=team_id,
            target_player_id=target_player_id,
            max_players_to_give=max_players
        )

        return jsonify({
            'team_id': team_id,
            'target_player_id': target_player_id,
            'fair_trades': trades,
            'count': len(trades)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to find fair trades: {str(e)}'}), 500


@bp.route('/trade/suggest', methods=['GET'])
def suggest_trades():
    """
    Get suggested trades to improve your roster.

    Query params:
        team_id: Your Ottoneu team ID (required)
        position: Specific position to improve (optional)
        league_id: Override configured league ID
    """
    team_id = request.args.get('team_id', type=int)
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400

    position = request.args.get('position')

    try:
        analyzer = get_trade_analyzer()
        suggestions = analyzer.suggest_trades(
            my_team_id=team_id,
            improve_position=position
        )

        return jsonify({
            'team_id': team_id,
            'position_focus': position,
            'suggestions': suggestions,
            'count': len(suggestions)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to suggest trades: {str(e)}'}), 500


@bp.route('/trade/market', methods=['GET'])
def analyze_trade_market():
    """
    Analyze the league trade market (buyers, sellers, opportunities).

    Query params:
        team_id: Your Ottoneu team ID (required)
        league_id: Override configured league ID
    """
    team_id = request.args.get('team_id', type=int)
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400

    try:
        analyzer = get_trade_analyzer()
        market = analyzer.analyze_league_trade_market(my_team_id=team_id)

        return jsonify({
            'team_id': team_id,
            **market
        })
    except Exception as e:
        return jsonify({'error': f'Market analysis failed: {str(e)}'}), 500
