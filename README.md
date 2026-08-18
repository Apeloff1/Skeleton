# Tutolage - Ultimate AI Learning Platform v15.0

<div align="center">

![Tutolage Logo](https://img.shields.io/badge/Tutolage-v15.0-6366F1?style=for-the-badge&logo=graduation-cap&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Expo](https://img.shields.io/badge/Expo-SDK_53-000020?style=for-the-badge&logo=expo&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248?style=for-the-badge&logo=mongodb&logoColor=white)

**The Ultimate AI-Powered Learning & Game Development Platform**

*Learn. Build. Create. Master.*

[Getting Started](#-quick-start) • [Features](#-features) • [Architecture](#-architecture) • [API Docs](#-api-documentation)

</div>

---

## 🎯 Vision

**Tutolage** is a comprehensive learning ecosystem that combines:

- **Intelligent AI Tutoring** with Jeeves, your personalized English butler AI companion
- **Game Development Pipelines** for creating NPCs, mechanics, and animations from natural language
- **Immersive Learning** with gamification, achievements, and managed learning curves
- **Co-Coding Mode** where Jeeves collaborates with you in real-time

---

## ✨ Features

### 🤖 Jeeves AI Tutor
- **20x Expanded Knowledge Base** - 2000+ concepts across 6 domains
- **3 System Law Blurbs** - 45,000 characters of pedagogical instruction
- **3 Self-Learning Matrices** - SAM, CLOM, KREM for optimal learning
- **ChromaDB RAG** - Long-term memory for personalized tutoring

### 🎮 Text-to-X Pipelines
| Pipeline | Description |
|----------|-------------|
| **Text-to-NPC** | Generate NPCs with personality, dialogue, AI behaviors |
| **Text-to-Game-Logic** | Create combat, economies, progression systems |
| **Text-to-Animation** | Generate skeletons, keyframes, state machines |

### 📚 Learning Systems
- **Immersive Tutor** - ZPD tracking, Socratic dialogue
- **Gamification** - XP, levels, achievements, daily quests
- **4 Learning Stages** - Onboarding → Foundation → Growth → Mastery

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ with [uv](https://github.com/astral-sh/uv)
- Node.js 20+ with yarn
- MongoDB 7.0+
- Docker (optional)

### Option 1: Docker (Recommended)

```bash
# Clone and start
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton

# Copy environment files
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Start all services
docker compose up -d

# Access:
# Frontend: http://localhost:3000
# Backend:  http://localhost:8001
# API Docs: http://localhost:8001/docs
```

### Option 2: Local Development

```bash
# Backend
cd backend
uv sync                    # Install dependencies with uv
uv run uvicorn server:app --reload --port 8001

# Frontend (new terminal)
cd frontend
yarn install
npx expo start
```

### Option 3: Traditional pip

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# Frontend
cd frontend
yarn install
npx expo start
```

---

## 🏗️ Architecture

```
tutolage/
├── backend/                    # FastAPI Backend
│   ├── routes/
│   │   ├── npc_pipeline.py          # Text-to-NPC
│   │   ├── game_logic_pipeline.py   # Text-to-Game-Logic
│   │   ├── animation_pipeline.py    # Text-to-Animation
│   │   ├── jeeves_core.py           # System Laws, Matrices, RAG
│   │   ├── jeeves_synergy.py        # Learning Integration
│   │   └── immersive_tutor.py       # Gamification & ZPD
│   ├── services/
│   │   ├── database.py              # MongoDB Service
│   │   └── rag_service.py           # ChromaDB RAG
│   ├── tests/                       # Pytest suite
│   ├── pyproject.toml               # Modern Python config (uv/ruff)
│   ├── Dockerfile
│   └── server.py
│
├── frontend/                   # Expo React Native
│   ├── app/
│   ├── components/
│   ├── features/
│   ├── store/                       # Zustand state
│   ├── Dockerfile
│   └── package.json
│
├── .github/workflows/ci.yml    # CI/CD Pipeline
├── docker-compose.yml          # One-command deployment
└── README.md
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI, MongoDB, ChromaDB, Pydantic |
| **Frontend** | Expo SDK 53, TypeScript, Zustand |
| **AI/ML** | OpenAI GPT-4o, ChromaDB RAG |
| **DevOps** | Docker, GitHub Actions, uv, ruff |

---

## 📖 API Documentation

### Pipelines

```bash
# NPC Pipeline
POST /api/npc-pipeline/generate
{"description": "A wise wizard", "include_dialogue": true}

# Game Logic Pipeline
POST /api/game-logic-pipeline/combat/generate
{"style": "turn_based", "include_magic": true}

# Animation Pipeline
POST /api/animation-pipeline/rig/generate
{"description": "humanoid", "include_fingers": true}
```

### Jeeves Core

```bash
# Get system laws
GET /api/jeeves-core/system-laws/all

# Get self-learning matrices
GET /api/jeeves-core/matrices

# Start co-coding session
POST /api/jeeves-core/co-coding/session
{"user_id": "user_1", "pipeline": "npc", "skill_level": "intermediate"}
```

Full API docs: `http://localhost:8001/docs`

---

## 🧪 Testing

```bash
cd backend

# Run all tests
uv run pytest

# With coverage
uv run pytest --cov=. --cov-report=html

# Specific test file
uv run pytest tests/test_npc_pipeline.py -v
```

---

## 🎓 Learning Stages

| Stage | Hours | Focus | Scaffolding |
|-------|-------|-------|-------------|
| 🌱 **Onboarding** | 0-5 | Confidence | Heavy |
| 🏗️ **Foundation** | 5-50 | Core Concepts | Moderate |
| 📈 **Growth** | 50-200 | Advanced | Light |
| 👑 **Mastery** | 200+ | Expertise | Minimal |

---

## 📸 Screenshots

| Feature | Location |
|---------|----------|
| Main IDE | Homepage |
| Command Palette | Grid icon (top-right) |
| Immersive Tutor | Learn → Immersive Tutor |
| Learning Hub | Learn → Learning Hub |
| Dashboard | Tools → Dashboard |

---

## 🤝 Contributing

```bash
# Setup pre-commit hooks
pip install pre-commit
pre-commit install

# Create feature branch
git checkout -b feature/amazing-feature

# Make changes, then commit
git commit -m "feat: add amazing feature"

# Push and create PR
git push origin feature/amazing-feature
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE)

---

<div align="center">

**Built with ❤️ for learners everywhere**

</div>
