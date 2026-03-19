# ✈ VoyageAI — Multi-Agent Travel & Event Planner

> An agentic AI system that plans, researches, and books trips end-to-end using Claude, MCP servers, and a human-in-the-loop approval flow.

![Status](https://img.shields.io/badge/status-prototype-amber?style=flat-square)
![Stack](https://img.shields.io/badge/stack-Claude%20%7C%20MCP%20%7C%20React-blue?style=flat-square)
![Approval](https://img.shields.io/badge/booking-human--in--the--loop-green?style=flat-square)

---

## What is VoyageAI?

VoyageAI is a multi-agent travel planning assistant. You describe a trip in plain language — *"Weekend in Goa next Friday, flights + hotel + beach party"* — and a coordinated team of AI agents handles discovery, conflict resolution, and booking, pausing to ask for your approval before anything is confirmed.

It is built on top of **Anthropic's Claude** as the reasoning backbone, with **MCP (Model Context Protocol)** servers providing live access to your Google Calendar and Gmail. The frontend is a clean dark dashboard showing live agent activity, trip cards, and an approval panel.

---

## Goals

- **Natural language trip planning** — no forms, no dropdowns. Describe what you want and let agents figure out the rest.
- **Real calendar awareness** — before suggesting anything, the Calendar agent checks your existing schedule for conflicts.
- **Multi-source research** — flights, hotels, and events are searched in parallel, then ranked and shortlisted by an orchestrator agent.
- **Human-in-the-loop approval** — nothing gets booked without your explicit sign-off. Every option comes with a price, a reason, and a way to reject or modify.
- **MCP-native** — Google Calendar and Gmail are connected as MCP servers, not scraped or simulated. The system reads real data and writes back real calendar events and confirmation emails.
- **Extensible agent architecture** — each agent (Calendar, Search, Email, Decision, Booking) is a standalone module that can be swapped, upgraded, or extended independently.

---

## Architecture

```
User request (natural language)
        │
        ▼
┌─────────────────────────┐
│     Orchestrator Agent  │  ← Claude (intent classification + routing)
└────────────┬────────────┘
             │ fans out in parallel
   ┌──────────┼───────────────┬──────────────┐
   ▼          ▼               ▼              ▼
Calendar   Search Agent   Email Agent   Preference Agent
  Agent    (web search)  (Gmail MCP)   (memory + rules)
(GCal MCP)
   └──────────┴───────────────┴──────────────┘
             │ results merged
             ▼
┌─────────────────────────┐
│  Decision + Conflict    │  ← ranks options, flags clashes
│  Resolver Agent         │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│     Approval Gate       │  ← user reviews + approves
└────────────┬────────────┘
             │ on approval
   ┌─────────┴──────────┐
   ▼                    ▼
Booking Agent     Confirmation Agent
(books + adds     (sends Gmail summary
 to GCal)          via MCP)
```

**Workflow types used:**
- **Sequential** — Orchestrator → Decision → Approval → Booking
- **Parallel** — Calendar, Search, Email, Preference agents run concurrently
- **Conditional** — Booking only proceeds after user approval; conflict logic branches on calendar state
- **Iterative** — Search agent re-queries if initial results are below quality threshold

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM backbone | Anthropic Claude (claude-sonnet-4-20250514) |
| Agent framework | Claude API with tool use / multi-turn |
| MCP servers | Google Calendar MCP, Gmail MCP |
| Web search | Claude web search tool |
| Frontend | React + Tailwind (or plain HTML/JS prototype) |
| Backend | Python (FastAPI) or Node.js |
| Memory / state | In-memory per session (Redis planned) |

---

## Project Structure

```
voyageai/
├── src/
│   ├── agents/
│   │   ├── orchestrator.py       # Intent classification, task routing
│   │   ├── calendar_agent.py     # Google Calendar MCP integration
│   │   ├── search_agent.py       # Web search for flights, hotels, events
│   │   ├── email_agent.py        # Gmail MCP — read confirmations
│   │   ├── decision_agent.py     # Rank options, detect conflicts
│   │   └── booking_agent.py      # Execute bookings, write to calendar
│   ├── mcp/
│   │   ├── gcal_client.py        # Google Calendar MCP wrapper
│   │   └── gmail_client.py       # Gmail MCP wrapper
│   ├── ui/
│   │   └── dashboard.html        # Prototype dashboard (single-file)
│   └── utils/
│       ├── llm.py                # Claude API helpers
│       └── state.py              # Trip state management
├── docs/
│   ├── architecture.md           # Detailed agent design
│   └── mcp-setup.md              # How to connect MCP servers
├── public/
│   └── demo-screenshot.png
├── .env.example
├── requirements.txt
├── package.json
└── README.md
```

---

## Planned Features

### Phase 1 — Core (current prototype)
- [x] Dashboard UI with trip cards, approval panel, agent log
- [x] Multi-agent architecture diagram and flow design
- [ ] Real Claude API integration for intent parsing
- [ ] Google Calendar MCP — live conflict checking
- [ ] Gmail MCP — read existing booking confirmations

### Phase 2 — Booking Intelligence
- [ ] Flight search via web tool (MakeMyTrip, Skyscanner scraping)
- [ ] Hotel search and ranking
- [ ] Event discovery (BookMyShow, Eventbrite, local listings)
- [ ] Budget constraints and preference memory
- [ ] Conflict auto-resolution suggestions

### Phase 3 — Full Automation
- [ ] Actual booking execution (API integrations or RPA)
- [ ] Post-trip: Gmail confirmation ingestion → auto-update trip cards
- [ ] Multi-trip conflict detection (overlapping trips)
- [ ] WhatsApp / Telegram notification on approval requests
- [ ] Itinerary PDF export

---

## Getting Started

### Prerequisites

- Python 3.11+ or Node.js 18+
- Anthropic API key
- Google Calendar MCP server configured
- Gmail MCP server configured

### Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/voyageai.git
cd voyageai

# Install dependencies
pip install -r requirements.txt

# Copy and fill environment variables
cp .env.example .env
# Add: ANTHROPIC_API_KEY, GCAL_MCP_URL, GMAIL_MCP_URL

# Run the prototype dashboard
open src/ui/dashboard.html
```

### Environment Variables

```env
ANTHROPIC_API_KEY=sk-ant-...
GCAL_MCP_URL=https://gcal.mcp.claude.com/mcp
GMAIL_MCP_URL=https://gmail.mcp.claude.com/mcp
```

---

## MCP Server Setup

VoyageAI uses two MCP servers for live data access:

**Google Calendar MCP** — checks availability, creates events post-booking
**Gmail MCP** — reads existing booking confirmation emails, sends trip summaries

See [`docs/mcp-setup.md`](docs/mcp-setup.md) for step-by-step configuration.

---

## Design Decisions

**Why MCP over direct API?**
MCP gives agents structured, permissioned access to real personal data without building custom OAuth flows for every service. It's the cleanest path to "agents that actually know your schedule."

**Why human-in-the-loop approval?**
Travel bookings are high-stakes and often non-refundable. The system is designed to do the heavy research work autonomously, but always pause before spending money. Confidence thresholds and auto-booking can be unlocked per category in a later phase.

**Why parallel agents?**
Calendar, flight, hotel, and event searches are independent. Running them in parallel cuts planning time significantly — from ~4 sequential calls to one concurrent batch.

---

## Contributing

This is an early-stage personal project. If you're exploring similar agentic patterns or want to extend it:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/booking-agent`)
3. Open a PR with a clear description of what the agent does and why

---

## License

MIT — use freely, build on it, share what you make.

---

*Built with Claude + MCP. Designed for humans who hate booking tabs.*
