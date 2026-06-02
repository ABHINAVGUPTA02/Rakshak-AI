# Rakshak AI 🛡️

Rakshak AI is an intelligent crime analytics and investigation platform designed to help law enforcement agencies move from reactive policing to proactive crime prevention. Inspired by modern intelligence systems, Rakshak AI unifies crime records, offender profiles, victim data, locations, and socio-economic indicators into a single knowledge graph that enables investigators to uncover hidden patterns, criminal associations, and emerging threats.

The platform combines **Knowledge Graphs**, **AI/ML**, **Natural Language Processing**, **Geospatial Analytics**, and **Explainable AI** to provide actionable intelligence through an intuitive conversational interface and interactive visualizations.

## Architecture

```
                    ┌─────────────────────┐
                    │ Data Sources        │
                    │                     │
                    │ FIRs                │
                    │ Crime Records       │
                    │ PDFs                │
                    │ Excel Sheets        │
                    │ Victim Data         │
                    │ Accused Data        │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Ingestion Layer     │
                    │                     │
                    │ OCR                 │
                    │ ETL                 │
                    │ Entity Extraction   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Data Enrichment     │
                    │                     │
                    │ Deduplication       │
                    │ Entity Resolution   │
                    │ Relationship Mining │
                    └──────────┬──────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
      ┌─────────────────┐            ┌─────────────────┐
      │ PostgreSQL      │            │ Neo4j           │
      │                 │            │ Knowledge Graph │
      └────────┬────────┘            └────────┬────────┘
               │                              │
               └──────────────┬───────────────┘
                              ▼
                  ┌─────────────────────┐
                  │ Intelligence Layer  │
                  │                     │
                  │ LLM                 │
                  │ Pattern Discovery   │
                  │ Forecasting         │
                  │ Anomaly Detection   │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ API Layer           │
                  │ FastAPI             │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ React Frontend      │
                  │                     │
                  │ Chatbot             │
                  │ Crime Map           │
                  │ Network Graph       │
                  │ Dashboards          │
                  └─────────────────────┘
```

## Key Features

### 🗣️ Conversational Crime Intelligence Assistant

- Query crime records using natural language in English and Kannada.
- Context-aware investigative conversations.

### 🕸️ Criminal Network Analysis

- Discover hidden relationships between offenders, victims, locations, vehicles, and financial entities.
- Visualize organized crime networks and repeat offender associations.

### 🗺️ Crime Hotspot & Geospatial Analytics

- Interactive district-level crime maps.
- Spatiotemporal hotspot detection and trend visualization.

### 🤖 AI-Powered Intelligence

- Crime pattern discovery.
- Anomaly detection.
- Predictive risk scoring and crime forecasting.

### 📊 Sociological & Criminological Insights

- Correlate crime with demographic and socio-economic indicators.
- Identify social risk factors and behavioral patterns.

### 🔍 Investigator Decision Support

- Automated case summaries.
- Similar case discovery.
- Evidence-backed investigative recommendations.

### 🔒 Explainable & Transparent AI

- Every insight is accompanied by evidence trails and reasoning paths.
- Designed for accountability and trust in law enforcement workflows.

## Vision

Rakshak AI aims to become a **Crime Intelligence Operating System** that transforms isolated records into connected intelligence, empowering investigators with faster insights, stronger evidence trails, and proactive crime prevention capabilities. 🚔✨

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React, TypeScript, Vite, Recharts |
| API | FastAPI, Python 3.11+ |
| Relational DB | PostgreSQL |
| Knowledge Graph | Neo4j |
| Intelligence | LLM (OpenAI-compatible), rule-based fallback |

## Project Structure

```
Rakshak-AI/
├── backend/          # FastAPI API, ingestion, intelligence services
├── frontend/         # React dashboard, chat, map, network graph
├── docker-compose.yml   # Compatible with podman compose
├── scripts/
│   ├── compose.sh       # Podman Compose wrapper
│   └── dev.sh           # Start DBs + API
└── .env.example
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- [Podman](https://podman.io/docs/installation)
- [podman-compose](https://github.com/containers/podman-compose) — `brew install podman-compose`

On macOS, start the Podman VM once: `podman machine start`

### 1. Start databases (optional — for PostgreSQL + Neo4j)

For the full stack with PostgreSQL and Neo4j knowledge graph:

```bash
cp .env.example .env
# Uncomment the PostgreSQL DATABASE_URL in .env
./scripts/compose.sh up -d
```

Or use the all-in-one dev script:

```bash
./scripts/dev.sh
```

Without Podman, the backend defaults to **SQLite** and runs with sample data. Neo4j graph features require Podman.

Neo4j Browser: http://localhost:7474  
PostgreSQL: `127.0.0.1:5433` (port 5433 avoids conflict with a local PostgreSQL on 5432)

#### Podman notes

- Uses `podman compose` (built-in) or `podman-compose` if available.
- The compose file is standard — no Docker required.
- Stop services: `./scripts/compose.sh down`
- View logs: `./scripts/compose.sh logs -f`

### 2. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/crimes` | List crime records |
| GET | `/api/v1/analytics/stats` | Crime statistics |
| GET | `/api/v1/analytics/hotspots` | District hotspots |
| GET | `/api/v1/graph/network` | Knowledge graph data |
| POST | `/api/v1/chat` | Intelligence assistant |
| POST | `/api/v1/ingest/upload` | Upload CSV, Excel, PDF, or image (OCR) |

## OCR & Document Ingestion

Rakshak AI supports multiple FIR data sources:

| Source | Processing |
|--------|------------|
| CSV / Excel | Structured column mapping |
| PDF (text) | Native text extraction |
| PDF (scanned) | OCR via Tesseract |
| Images (JPG, PNG, TIFF) | OCR via Tesseract |

### OCR setup (macOS)

```bash
brew install tesseract tesseract-lang
```

Configure languages in `.env` (English + Kannada by default):

```bash
OCR_LANGUAGES=eng+kan
OCR_DPI=300
```

When a FIR number cannot be read from the document, a temporary ID like `FIR/OCR/AB12CD34` is assigned. Parsed fields (district, crime type, accused/victim) are extracted automatically and can be reviewed in the Crime Records table.
