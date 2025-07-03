# Pokédex Deep Research 
Pokédex Deep Research is a research-focused AI that answers complex Pokémon questions by planning, executing, and evaluating steps with tools based on PokéAPI and optional web search.

## ⚡ Quickstart

### 1. Create `.env` file

```env
OPENAI_API_KEY=<openai_api_key>
TAVILY_API_KEY=<tavily_api_key>       # optional - enables web search tool
LOGFIRE_API_KEY=<logfire_api_key>     # optional - enables observability/logging
```

### 2. Build the Docker image

```bash
docker build -t pokedex-agent . --no-cache
```

### 3. Run the container

```bash
docker run --env-file .env -p 8000:8000 pokedex-agent
```

---

## 🎯 What It Does

Supports rich, open-ended Pokémon queries like:

- “Build a team of all bug-type Pokémon.”
- “What’s an easy Pokémon to train in Pokémon Ruby?”
- “Find a unique Pokémon that lives by the sea.”
- “What Pokémon should I add next to my party?”

---

## Design Notes

### 🛠 Tools

The agent uses purpose-built tools with compact, LLM-ready outputs:

- **`get_pokemon_profiles`**  
  Fetch profile, battle, location, move, and lore data per Pokémon.

- **`search_pokemon_by_criteria`**  
  Advanced multi-field search based on types, stats, roles, resistances, and ecological traits.

- **`analyse_pokemon_team`**  
  Evaluates a team’s coverage, weaknesses, resistances, speed tiers, and role distribution.

- **`search_pokemon_web`** *(optional)*  
  Searches trusted Pokémon sites (e.g., Serebii, Bulbapedia, Smogon) using Tavily. Useful for qualitative or lore-based questions.

Each tool returns minimized, structured strings with:
- Reduced verbosity
- Merged or deduplicated fields
- LLM-controllable scopes (e.g., detail of information)


### 🧬 Dataset

Scraped from [PokéAPI](https://pokeapi.co/) and enhanced with:

- `.parquet` for fast loading and querying with `pandas`
- LLM-friendly JSON format with reduced verbosity
- Type chart data for weakness/resistance logic
- Tiered numerical values (e.g., stats) for easier filtering
- Enums for stat categories, roles, tags, habitats, etc.

### 🧪 Agent Loop

The core research loop is inspired by [TogetherAI's Open Deep Research](https://www.together.ai/blog/open-deep-research):

1. **Plan** — Break query into parallel subtasks  
2. **Execute** — Call tools based on queries 
3. **Evaluate** — Determine if collected results are sufficient  
4. **Repeat** — Re-plan if needed or summarize response 
5. **Report** — Write comprehensive report with results

Tokens are managed by:
- Carefully crafted prompts
- Limiting tool retries
- Usage limits per execute agent call
- Hard max iteration limits

Error handling and agent summaries converts tool failures into clear, actionable messages for the planning agent.

### 🧠 Models

The system uses a combination thinking and general-purpose models to balance reasoning and response time.

---

## 📁 Project Layout

```
.
├── app.py                     # Chainlit entry point
├── agents/
│   ├── agents.py              # Plan-evaluate logic
│   ├── graph.py               # Pydantic execution graph
│   ├── models.py              # State and schema definitions
│   └── prompts.py             # Prompt templates
├── dataset/
│   ├── build_dataset.py       # Raw data scraping and processing
│   ├── generate_types.py      # Type generation for Pokémon info
│   ├── type_chart.py          # Type chart generation
│   └── utils.py
├── resources/
│   ├── enums.py               # Tool input enums
│   ├── pokemon.json           # Raw PokéAPI data
│   ├── pokemon.parquet        # LLM-ready Pokémon data
│   └── type_chart.json        # Pokémon type chart
├── tools/
│   ├── analyse_pokemon_team.py
│   ├── get_pokemon_profiles.py
│   ├── search_pokemon_by_criteria.py
│   └── search_pokemon_web.py  
└── pyproject.toml              
```