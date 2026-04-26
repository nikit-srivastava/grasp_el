from grasp.manager import KgManager
from grasp.sparql.utils import find, parse_string, parse_to_string

STOP_FUNCTION = {
    "name": "stop",
    "description": "Stop the setup process.",
}


def set_description_function(description: str) -> dict:
    return {
        "name": "set_description",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "The description",
                },
            },
            "required": ["description"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def index_functions() -> list[dict]:
    return [
        {
            "name": "show_setup",
            "description": "Show the current index and info SPARQL queries for the knowledge graph.",
        },
        {
            "name": "set_query",
            "description": "Set the index or info SPARQL query for the knowledge graph",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["index", "info"],
                        "description": "Whether this is an index query or an info query",
                    },
                    "sparql": {
                        "type": "string",
                        "description": "The SPARQL query",
                    },
                },
                "required": ["type", "sparql"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        set_description_function(
            "Set a concise description of what this index contains and how it is built. "
            "Typically a single sentence is sufficient."
        ),
        STOP_FUNCTION,
    ]


def info_functions() -> list[dict]:
    return [
        {
            "name": "show_setup",
            "description": "Show the current prefixes and description of the knowledge graph.",
        },
        {
            "name": "add_prefix",
            "description": "Add a new prefix for the knowledge graph, mapping a short "
            "prefix name to its full IRI namespace (e.g. 'wd' for "
            "'http://www.wikidata.org/entity/'). Only knowledge graph specific "
            "prefixes need to be added - common prefixes like rdf, rdfs, and "
            "xsd are available by default.",
            "parameters": {
                "type": "object",
                "properties": {
                    "short": {
                        "type": "string",
                        "description": "The short prefix name (e.g. 'wd')",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "The full IRI namespace (e.g. 'http://www.wikidata.org/entity/')",
                    },
                },
                "required": ["short", "namespace"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "delete_prefix",
            "description": "Delete an existing knowledge graph prefix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "short": {
                        "type": "string",
                        "description": "The short prefix name to delete",
                    },
                },
                "required": ["short"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "update_prefix",
            "description": "Update the namespace of an existing knowledge graph prefix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "short": {
                        "type": "string",
                        "description": "The short prefix name to update",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "The new full IRI namespace",
                    },
                },
                "required": ["short", "namespace"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        set_description_function(
            "Set a concise description of what the knowledge graph contains. "
            "Typically a single sentence about the domain and scope of the "
            "knowledge graph is sufficient."
        ),
        STOP_FUNCTION,
    ]


def find_select_clause(parse: dict) -> str:
    clause = find(parse, "SelectClause")
    if clause is None:
        raise ValueError("No SELECT clause found in query")
    return parse_to_string(clause)


def find_solution_modifier(parse: dict) -> str:
    sol_mod = find(parse, "SolutionModifier")
    if sol_mod is None:
        raise ValueError("No solution modifier found in query")
    return parse_to_string(sol_mod)


def validate_select_clause(parse: dict, target: str):
    select = find_select_clause(parse)
    if select.replace(" ", "") != target.replace(" ", ""):
        raise ValueError(f"SELECT clause must be '{target}'")


def validate_solution_modifier(parse: dict, target: str):
    sol_mod = find_solution_modifier(parse)
    if sol_mod.replace(" ", "") != target.replace(" ", ""):
        raise ValueError(f"Solution modifier must be '{target}'")


INDEX_SPARQL_SELECT = "SELECT ?id ?value ?tags"
INDEX_SPARQL_SOL_MOD = "ORDER BY DESC(?score) ?id DESC(?tags)"


def validate_index_sparql(manager: KgManager, sparql: str):
    parse, _ = parse_string(sparql, manager.sparql_parser)

    validate_select_clause(parse, INDEX_SPARQL_SELECT)
    validate_solution_modifier(parse, INDEX_SPARQL_SOL_MOD)


INFO_SPARQL_SELECT = "SELECT ?id ?value ?type"
INFO_SPARQL_SOL_MOD = "ORDER BY ?id ?type ?value"


def validate_info_sparql(manager: KgManager, sparql: str):
    parse, _ = parse_string(sparql, manager.sparql_parser)

    validate_select_clause(parse, INFO_SPARQL_SELECT)
    validate_solution_modifier(parse, INFO_SPARQL_SOL_MOD)
