# Crypto Funding Rate Dashboard

A high-performance real-time dashboard for monitoring cryptocurrency funding rates across multiple exchanges (Binance, Bybit, Bitget, OKX, Gate, CoinW, etc.).

## 🚀 Features

- **Real-time Monitoring**: Live funding rate updates via WebSockets.
- **Historical Analysis**: Interactive charts showing funding rate trends over time.
- **Spread Analysis**: Compare funding rates across different exchanges to find arbitrage opportunities.
- **Multi-Exchange Support**: Integrated with major exchanges including Binance, Bybit, Bitget, Gate.io, MEXC, KuCoin, and CoinW.
- **Professional UI**: "QuantMatrix" dark-themed dashboard with high-contrast heatmaps and responsive design.
- **High Performance**: Optimized backend with Redis caching and PostgreSQL partitioned tables for efficient data storage.

## 🛠 Tech Stack

- **Frontend**: React, TypeScript, Tailwind CSS, Vite, Recharts.
- **Backend**: Python, FastAPI, SQLAlchemy, CCXT.
- **Data Storage**: PostgreSQL (Time-series optimization), Redis.
- **Infrastructure**: Docker, Docker Compose.

## 📦 Installation & Setup

### Prerequisites
- Docker & Docker Compose
- (Optional) Python 3.10+ & Node.js 18+ for local development

### Quick Start with Docker
1. Clone the repository:
   ```bash
   git clone git@github.com:yourusername/crypto-funding-rate.git
   cd crypto-funding-rate
   ```

2. Start the services:
   ```bash
   docker-compose up --build -d
   ```

3. Access the dashboard:
   - Frontend: `http://localhost:5173`
   - Backend API: `http://localhost:8000/docs`

## 📖 Directory Structure

- `/backend`: FastAPI application and data collectors.
- `/frontend`: React dashboard source code.
- `/research`: (Local only) Scripts and experiments for API discovery.

## 📄 License

MIT License
