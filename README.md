# Ottoneu Fantasy Baseball Roster Tool

A web application to help make roster decisions for Ottoneu fantasy baseball leagues by aggregating data from multiple sources.

## Data Sources

- **Fangraphs** - Player projections, statistics, and valuations
- **Ottoneu** - League-specific rosters, salaries, and auction values
- **Baseball Savant** - Statcast data including expected stats, pitch data, and advanced metrics

## Project Structure

```
├── backend/
│   ├── api/              # API endpoints
│   ├── data_sources/     # Data fetchers for each source
│   ├── models/           # Data models
│   └── utils/            # Helper utilities
├── frontend/
│   ├── static/           # CSS, JS, images
│   └── templates/        # HTML templates
├── tests/                # Test files
├── data/                 # Cached data files
├── app.py                # Main application entry point
├── config.py             # Configuration settings
└── requirements.txt      # Python dependencies
```

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure your settings in `config.py` (add your Ottoneu league ID, etc.)

4. Run the application:
   ```bash
   python app.py
   ```

## Features (Planned)

- [ ] View player projections with multiple projection systems
- [ ] Compare players across key metrics
- [ ] Import your Ottoneu league rosters and salaries
- [ ] Identify undervalued free agents
- [ ] Track player value vs. salary over time
- [ ] Statcast-based player analysis

## License

MIT
