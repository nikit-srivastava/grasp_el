from grasp.manager import KgManager
from grasp.sparql.utils import (
    find,
    find_all,
    parse_string,
)


def setup_functions() -> list[dict]:
    return [
        {
            "name": "set_query",
            "description": """\
Set a SPARQL query for building an index or retrieving info for entities or properties.

Index SPARQLs must be SELECT queries returning ?id, ?value, and ?tags variables. \
?id is the entity/property IRI, ?value is a searchable text field (like a label or \
alias), and ?tags should be "main" for the primary label. Results should be ordered \
descending by some score (e.g., frequency or popularity, used for resolving \
ties in search results) and then by id.

Info SPARQLs must be SELECT queries returning ?id, ?value, and ?type variables, and \
must contain the placeholder {IDS} (to be replaced with a VALUES clause of \
entity/property IRIs at query time). ?type should be "label", "alias", or "info".""",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "enum": ["entity", "property"],
                        "description": "Whether this query is for entities or properties",
                    },
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
                "required": ["index", "type", "sparql"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "set_prefix",
            "description": """\
Set a prefix for the knowledge graph, mapping a short prefix name to its full \
IRI namespace (e.g. "wd" and "http://www.wikidata.org/entity/"). Only knowledge \
graph specific prefixes need to be set - common prefixes like rdf, rdfs, and \
xsd are available by default.""",
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
            "name": "set_description",
            "description": "Set a concise description of what the knowledge graph contains. \
Typically a single sentence about the domain and scope of the knowledge graph is sufficient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "A concise description of the knowledge graph",
                    },
                },
                "required": ["description"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "stop",
            "description": "Stop the setup process.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


INDEX_SPARQL_VARS = {"id", "value", "tags"}
INFO_SPARQL_VARS = {"id", "value", "type"}


def find_select_vars(parse: dict) -> set[str]:
    clause = find(parse, "SelectClause")
    if clause is None:
        raise ValueError("No SELECT clause found in query")

    used = set()
    for var in find_all(clause, "Var"):
        used.add(var["children"][0]["value"].lstrip("?").lstrip("$"))

    return used


def validate_sparql(manager: KgManager, sparql: str, required: set[str]):
    parse, _ = parse_string(sparql, manager.sparql_parser)

    used = find_select_vars(parse)

    missing = required - used
    if missing:
        missing_str = ", ".join(f"?{v}" for v in sorted(missing))
        raise ValueError(f"Missing required variables {missing_str} in SELECT clause.")
