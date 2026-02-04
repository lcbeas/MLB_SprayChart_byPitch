"""
Ottoneu Fantasy Baseball Roster Tool
Main application entry point
"""

from flask import Flask, render_template, jsonify
from backend.api import player_api, league_api, analysis_api, ml_api
from config import Config

app = Flask(__name__,
            template_folder='frontend/templates',
            static_folder='frontend/static')
app.config.from_object(Config)

# Register blueprints
app.register_blueprint(player_api.bp, url_prefix='/api/players')
app.register_blueprint(league_api.bp, url_prefix='/api/league')
app.register_blueprint(analysis_api.bp, url_prefix='/api/analysis')
app.register_blueprint(ml_api.bp, url_prefix='/api/ml')


@app.route('/')
def index():
    """Render the main dashboard."""
    return render_template('index.html')


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    app.run(debug=Config.DEBUG, port=Config.PORT)
