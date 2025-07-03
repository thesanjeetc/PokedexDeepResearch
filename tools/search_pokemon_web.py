import os
from tavily import TavilyClient


api_key = os.getenv("TAVILY_API_KEY")
client = TavilyClient(api_key)


async def search_pokemon_web(query: str):
    """
    Performs a targeted web search across a curated list of reliable Pokémon-centric websites to answer a query. This tool is best used for questions that require up-to-date, community-driven, or qualitative information that may not be available in a structured database. Examples include competitive strategies (from Smogon), detailed lore explanations, opinions, or answers to very specific or obscure questions. It leverages a powerful search API to synthesize a direct answer from the following trusted sources: Serebii, Bulbapedia, PokémonDB, and Smogon.

    Args:
        query (str): The natural language question or search term about any Pokémon-related topic. For example: "What is the best nature for a competitive Garchomp?", "Explain the lore behind the Legendary Beasts of Johto.", or "How to evolve Galarian Farfetch'd?".

    Returns:
        str: A synthesized, natural language answer to the query, compiled from the search results from the trusted Pokémon websites. If no definitive answer can be found, it may return a summary of the most relevant search results.
    """
    response = client.search(
        query=query,
        search_depth="advanced",
        include_answer="advanced",
        chunks_per_source=5,
        include_domains=[
            "https://www.serebii.net/",
            "https://bulbapedia.bulbagarden.net/",
            "https://pokemondb.net/",
            "https://www.smogon.com/",
        ],
    )
    return response["answer"]
